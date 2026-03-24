import logging
from decimal import Decimal
from typing import Optional

import requests
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pgvector.django import CosineDistance

from hypothalamus.models import (
    AIMode,
    AIModel,
    AIModelCapabilities,
    AIModelDescription,
    AIModelDescriptionCache,
    AIModelPricing,
    AIModelProvider,
    AIModelProviderUsageRecord,
    AIModelSyncLog,
    AIModelTags,
    LLMProvider,
    SyncStatus,
)

LITELLM_CATALOG_URL = (
    'https://raw.githubusercontent.com/BerriAI/litellm/main'
    '/model_prices_and_context_window.json'
)
OPENROUTER_MODELS_URL = 'https://openrouter.ai/api/v1/models'

CATALOG_SKIP_KEYS = frozenset({'sample_spec'})
CHAT_MODE = 'chat'

logger = logging.getLogger(__name__)


def _dec(key: str, data: dict) -> Decimal:
    return Decimal(str(data.get(key) or 0.0))


class Hypothalamus:
    @staticmethod
    def pick_optimal_model(ledger: AIModelProviderUsageRecord) -> bool:
        disc = ledger.identity_disc

        payload_size = (
            len(str(ledger.request_payload)) + len(str(ledger.tool_payload))
        ) // 4

        max_cost = (
            disc.budget.max_input_cost_per_token
            if hasattr(disc, 'budget') and disc.budget
            else 0
        )

        valid_provider_ids = [
            p.id
            for p in LLMProvider.objects.all()
            if not p.requires_api_key or p.has_active_key
        ]

        breaker_filter = Q(rate_limit_reset_time__isnull=True) | Q(
            rate_limit_reset_time__lte=timezone.now()
        )

        filters = {
            'provider_id__in': valid_provider_ids,
            'mode__name': 'chat',
            'ai_model__enabled': True,
            'aimodelpricing__is_current': True,
            'aimodelpricing__is_active': True,
            'aimodelpricing__input_cost_per_token__lte': max_cost,
            'ai_model__context_length__gte': payload_size,
        }

        # Checking dynamic capabilities instead of hardcoded booleans
        if ledger.tool_payload:
            filters['ai_model__capabilities__name'] = 'function_calling'

        best = (
            AIModelProvider.objects.filter(breaker_filter, **filters)
            .annotate(distance=CosineDistance('ai_model__vector', disc.vector))
            .select_related('ai_model')
            .order_by('distance', 'aimodelpricing__input_cost_per_token')
            .first()
        )

        if not best:
            return False

        ledger.ai_model_provider = best
        ledger.ai_model = best.ai_model

        pricing = best.aimodelpricing_set.filter(is_current=True).first()
        if pricing:
            ledger.input_cost_per_token = pricing.input_cost_per_token
            ledger.output_cost_per_token = pricing.output_cost_per_token
            ledger.input_cost_per_token_above_128k_tokens = (
                pricing.input_cost_per_token_above_128k_tokens
            )
            ledger.output_cost_per_token_above_128k_tokens = (
                pricing.output_cost_per_token_above_128k_tokens
            )
            ledger.output_cost_per_reasoning_token = (
                pricing.output_cost_per_reasoning_token
            )
            ledger.cache_read_input_token_cost = (
                pricing.cache_read_input_token_cost
            )
            ledger.cache_creation_input_token_cost = (
                pricing.cache_creation_input_token_cost
            )
            ledger.input_cost_per_audio_token = (
                pricing.input_cost_per_audio_token
            )

        return True

    @classmethod
    def sync_catalog(
        cls, use_local_cache: bool = False, force_rebuild: bool = False
    ) -> Optional[AIModelSyncLog]:
        running_status = SyncStatus.objects.get(id=SyncStatus.RUNNING)

        if AIModelSyncLog.objects.filter(status=running_status).exists():
            logger.warning('[Hypothalamus] Sync already running. Aborting.')
            return None

        sync_log = AIModelSyncLog.objects.create(status=running_status)
        active_provider_keys: set[str] = set()
        models_flagged_for_vector_update = set()

        try:
            logger.info('[Hypothalamus] Fetching LiteLLM catalog...')
            response = requests.get(LITELLM_CATALOG_URL, timeout=30)
            response.raise_for_status()
            catalog: dict = response.json()

            with transaction.atomic():
                for raw_key, data in catalog.items():
                    if raw_key in CATALOG_SKIP_KEYS:
                        continue

                    active_provider_keys.add(raw_key)

                    provider = cls._ensure_provider(data)
                    mode = cls._ensure_mode(data)
                    ai_model, model_created = cls._ensure_ai_model(
                        raw_key, data
                    )

                    if model_created:
                        sync_log.models_added += 1
                        models_flagged_for_vector_update.add(ai_model.id)

                    model_provider = cls._ensure_model_provider(
                        raw_key, ai_model, provider, mode, data
                    )
                    price_updated = cls._update_pricing(model_provider, data)
                    if price_updated:
                        sync_log.prices_updated += 1

                dead = AIModelPricing.objects.filter(
                    is_current=True, is_active=True
                ).exclude(
                    model_provider__provider_unique_model_id__in=active_provider_keys
                )
                sync_log.models_deactivated = dead.count()
                dead.update(is_active=False)

            # --- THE SEMANTIC ETL PHASE ---
            enriched_model_ids = cls.enrich_model_semantics_from_openrouter(
                use_local_cache=use_local_cache, force_rebuild=force_rebuild
            )
            models_flagged_for_vector_update.update(enriched_model_ids)

            # If we are forcing a rebuild, ensure ALL models get re-vectorized
            if force_rebuild:
                all_model_ids = set(
                    AIModel.objects.values_list('id', flat=True)
                )
                models_flagged_for_vector_update.update(all_model_ids)

            sync_log.status = SyncStatus.objects.get(id=SyncStatus.SUCCESS)

        except Exception as exc:
            logger.exception('[Hypothalamus] Sync failed.')
            sync_log.status = SyncStatus.objects.get(id=SyncStatus.FAILED)
            sync_log.error_message = str(exc)

        finally:
            sync_log.save()
            if (
                sync_log.status_id == SyncStatus.SUCCESS
                and models_flagged_for_vector_update
            ):
                cls._trigger_vector_generation(models_flagged_for_vector_update)

        return sync_log

    # ------------------------------------------------------------------ #
    #  Private helpers                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _ensure_provider(data: dict) -> LLMProvider:
        slug = data.get('litellm_provider', 'unknown')
        provider, _ = LLMProvider.objects.get_or_create(
            key=slug,
            defaults={'name': slug.title(), 'base_url': ''},
        )
        return provider

    @staticmethod
    def _ensure_mode(data: dict) -> AIMode:
        slug = data.get('mode', CHAT_MODE)
        mode, _ = AIMode.objects.get_or_create(name=slug)
        return mode

    @staticmethod
    def _ensure_ai_model(raw_key: str, data: dict) -> tuple[AIModel, bool]:
        model_name = raw_key.split('/')[-1] if '/' in raw_key else raw_key

        ai_model, created = AIModel.objects.get_or_create(
            name=model_name,
            defaults={
                'context_length': (
                    data.get('max_input_tokens')
                    or data.get('max_tokens')
                    or 4096
                ),
            },
        )

        capabilities_to_add = []
        for key, value in data.items():
            if key.startswith('supports_') and value is True:
                cap_name = key.replace('supports_', '')
                cap_obj, _ = AIModelCapabilities.objects.get_or_create(
                    name=cap_name
                )
                capabilities_to_add.append(cap_obj)

        if capabilities_to_add:
            ai_model.capabilities.add(*capabilities_to_add)

        return ai_model, created

    @staticmethod
    def _ensure_model_provider(
        raw_key: str,
        ai_model: AIModel,
        provider: LLMProvider,
        mode: AIMode,
        data: dict,
    ) -> AIModelProvider:
        model_provider, _ = AIModelProvider.objects.update_or_create(
            provider_unique_model_id=raw_key,
            defaults={
                'ai_model': ai_model,
                'provider': provider,
                'max_tokens': data.get('max_tokens'),
                'max_input_tokens': data.get('max_input_tokens'),
                'max_output_tokens': data.get('max_output_tokens'),
                'mode': mode,
            },
        )
        return model_provider

    @staticmethod
    def _update_pricing(model_provider: AIModelProvider, data: dict) -> bool:
        in_cost = _dec('input_cost_per_token', data)
        out_cost = _dec('output_cost_per_token', data)

        current = AIModelPricing.objects.filter(
            model_provider=model_provider, is_current=True
        ).first()

        if (
            current
            and current.input_cost_per_token == in_cost
            and current.output_cost_per_token == out_cost
        ):
            return False

        if current:
            current.is_current = False
            current.save(update_fields=['is_current'])

        AIModelPricing.objects.create(
            model_provider=model_provider,
            is_current=True,
            is_active=True,
            input_cost_per_token=in_cost,
            output_cost_per_token=out_cost,
            input_cost_per_token_above_128k_tokens=_dec(
                'input_cost_per_token_above_128k_tokens', data
            ),
            output_cost_per_token_above_128k_tokens=_dec(
                'output_cost_per_token_above_128k_tokens', data
            ),
            output_cost_per_reasoning_token=_dec(
                'output_cost_per_reasoning_token', data
            ),
            cache_read_input_token_cost=_dec(
                'cache_read_input_token_cost', data
            ),
            cache_creation_input_token_cost=_dec(
                'cache_creation_input_token_cost', data
            ),
            input_cost_per_audio_token=_dec('input_cost_per_audio_token', data),
        )
        return True

    @classmethod
    def enrich_model_semantics_from_openrouter(
        cls, use_local_cache: bool = False, force_rebuild: bool = False
    ) -> set:
        """
        Hits OpenRouter, extracts descriptions AND architecture data.
        UPGRADE: Now acts as an authoritative source for OpenRouter models,
        creating missing models and enforcing OpenRouter's live pricing.
        """
        logger.info(
            '[Hypothalamus] Enriching and syncing OpenRouter authoritative data...'
        )
        modified_model_ids = set()

        try:
            payload = None

            if use_local_cache:
                latest_cache = AIModelDescriptionCache.objects.order_by(
                    '-created_at'
                ).first()
                if latest_cache:
                    logger.info('[Hypothalamus] Using local OpenRouter cache.')
                    payload = latest_cache.cached_library
                else:
                    logger.warning(
                        '[Hypothalamus] No local cache found. Falling back to network.'
                    )

            if not payload:
                logger.info(
                    '[Hypothalamus] Fetching OpenRouter models from network...'
                )
                response = requests.get(OPENROUTER_MODELS_URL, timeout=15)
                response.raise_for_status()
                payload = response.json()
                AIModelDescriptionCache.objects.create(cached_library=payload)

            openrouter_models = payload.get('data', [])

            # Ensure we have the OpenRouter LLMProvider and Chat Mode ready
            or_llm_provider, _ = LLMProvider.objects.get_or_create(
                key='openrouter', defaults={'name': 'OpenRouter'}
            )
            chat_mode, _ = AIMode.objects.get_or_create(name=CHAT_MODE)

            length = len(openrouter_models)
            counter = 0
            for or_data in openrouter_models:
                counter += 1
                logger.info(
                    f'Processing OpenRouter model {counter} of {length}'
                )
                stripped_id = or_data['id']
                provider_unique_id = f'openrouter/{stripped_id}'
                new_desc = or_data.get('description', '')

                # 1. Ensure AIModel exists
                ai_model, model_created = AIModel.objects.get_or_create(
                    name=or_data.get('name', stripped_id),
                    defaults={
                        'context_length': or_data.get('context_length', 4096),
                    },
                )

                # --- NEW: Capability Inheritance for OpenRouter Variants ---
                # If this model has a suffix (e.g. google/gemini-2.5-flash:free)
                # it inherits the capabilities (like function_calling) of its parent.
                if ':' in stripped_id:
                    base_id = stripped_id.split(':')[0]
                    base_provider_unique_id = f'openrouter/{base_id}'

                    base_provider = (
                        AIModelProvider.objects.filter(
                            provider_unique_model_id=base_provider_unique_id
                        )
                        .select_related('ai_model')
                        .first()
                    )

                    if base_provider and base_provider.ai_model:
                        base_caps = base_provider.ai_model.capabilities.all()
                        if base_caps.exists():
                            # M2M .add() is idempotent, it won't duplicate them
                            ai_model.capabilities.add(*base_caps)

                # Fallback: Guess from the OpenRouter description
                if not ai_model.capabilities.filter(
                    name='function_calling'
                ).exists():
                    desc_lower = new_desc.lower()
                    if (
                        'function calling' in desc_lower
                        or 'tool use' in desc_lower
                        or 'tools' in desc_lower
                    ):
                        fc_cap, _ = AIModelCapabilities.objects.get_or_create(
                            name='function_calling'
                        )
                        ai_model.capabilities.add(fc_cap)
                # ---------------------------------------------------------

                # 2. Ensure AIModelProvider exists
                provider, _ = AIModelProvider.objects.update_or_create(
                    provider_unique_model_id=provider_unique_id,
                    defaults={
                        'ai_model': ai_model,
                        'provider': or_llm_provider,
                        'mode': chat_mode,
                        'max_input_tokens': or_data.get('context_length'),
                    },
                )

                # 3. ENFORCE OPENROUTER PRICING
                or_pricing = or_data.get('pricing', {})
                in_cost = _dec('prompt', or_pricing)
                out_cost = _dec('completion', or_pricing)

                mocked_price_data = {
                    'input_cost_per_token': in_cost,
                    'output_cost_per_token': out_cost,
                }
                cls._update_pricing(provider, mocked_price_data)

                # 4. SEMANTIC ENRICHMENT (Tags and Description)
                arch = or_data.get('architecture', {})
                extracted_tags = []
                if arch.get('modality'):
                    extracted_tags.append(f'modality:{arch["modality"]}')
                if arch.get('instruct_type'):
                    extracted_tags.append(f'instruct:{arch["instruct_type"]}')

                current_desc_obj = AIModelDescription.objects.filter(
                    ai_models=ai_model, is_current=True
                ).first()

                is_different = (
                    not current_desc_obj
                    or current_desc_obj.description != new_desc
                )

                if new_desc and (is_different or force_rebuild):
                    if current_desc_obj:
                        current_desc_obj.is_current = False
                        current_desc_obj.save(update_fields=['is_current'])

                    desc_obj = AIModelDescription.objects.create(
                        description=new_desc, is_current=True
                    )
                    desc_obj.ai_models.add(ai_model)

                    for tag_string in extracted_tags:
                        tag_obj, _ = AIModelTags.objects.get_or_create(
                            name=tag_string
                        )
                        desc_obj.tags.add(tag_obj)

                    modified_model_ids.add(ai_model.id)

        except Exception:
            logger.exception(
                '[Hypothalamus] OpenRouter semantic enrichment failed.'
            )

        return modified_model_ids

    @classmethod
    def _trigger_vector_generation(cls, target_model_ids: set):
        models_to_embed = AIModel.objects.filter(
            Q(id__in=target_model_ids) | Q(vector__isnull=True)
        )

        logger.info(
            '[Hypothalamus] Vectorizing %d models.', models_to_embed.count()
        )
        count = models_to_embed.count()
        counter = 0
        for model in models_to_embed:
            counter += 1
            logger.info(f'Processing model {counter} of {count}')
            model.update_vector()
