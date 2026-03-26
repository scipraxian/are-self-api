import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

import requests
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pgvector.django import CosineDistance

from hypothalamus.model_semantic_parser import parse_model_string
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
    LiteLLMCache,
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
    def pick_optimal_model(
        ledger: AIModelProviderUsageRecord, attempt: int = 0
    ) -> bool:
        disc = ledger.identity_disc
        # 1. Resolve Selection Policy (Identity-level or default)
        filter_obj = disc.selection_filter if disc else None
        strategy_obj = filter_obj.failover_strategy if filter_obj else None

        # 2. Extract baseline constraints
        payload_size = (
            len(str(ledger.request_payload)) + len(str(ledger.tool_payload))
        ) // 4

        valid_provider_ids = [
            p.id
            for p in LLMProvider.objects.all()
            if not p.requires_api_key or p.has_active_key
        ]

        breaker_filter = Q(rate_limit_reset_time__isnull=True) | Q(
            rate_limit_reset_time__lte=timezone.now()
        )

        # Baseline filters matching all candidate models (Pricing removed!)
        filters = {
            'provider_id__in': valid_provider_ids,
            'mode__name': 'chat',
            'ai_model__enabled': True,
            'is_enabled': True,
            'ai_model__context_length__gte': payload_size,
        }

        # FIX 1 (Updated): Dynamically apply pricing filters ONLY if a budget is enforced
        max_cost = None
        if disc and hasattr(disc, 'identitybudgetassignment_set'):
            assignment = disc.identitybudgetassignment_set.filter(
                is_active=True
            ).first()
            if assignment and assignment.budget:
                max_cost = assignment.budget.max_input_cost_per_token

        if max_cost is not None:
            filters['aimodelpricing__is_current'] = True
            filters['aimodelpricing__is_active'] = True
            filters['aimodelpricing__input_cost_per_token__lte'] = max_cost

        # Hard Exclusions (Global + Filter-specific)
        excludes = {}
        if ledger.tool_payload:
            filters['ai_model__capabilities__name'] = 'function_calling'
            excludes['disabled_capabilities__name'] = 'function_calling'

        if filter_obj:
            banned = filter_obj.banned_providers.values_list('id', flat=True)
            if banned:
                excludes['provider_id__in'] = list(banned)

        # Compile into a Base QuerySet to allow chained capability filtering
        base_qs = AIModelProvider.objects.filter(
            breaker_filter, **filters
        ).exclude(**excludes)

        if filter_obj:
            req_caps = filter_obj.required_capabilities.values_list(
                'id', flat=True
            )
            for cap_id in req_caps:
                base_qs = base_qs.filter(ai_model__capabilities__id=cap_id)

        # 3. Determine the Current Selection Strategy Step
        best = None

        # PRIORITY 0: The Preferred Model (Locked to attempt 0)
        if attempt == 0 and filter_obj and filter_obj.preferred_model:
            best = base_qs.filter(id=filter_obj.preferred_model_id).first()
            if best:
                ledger.ai_model_provider = best
                ledger.ai_model = best.ai_model
                return Hypothalamus._finalize_ledger(ledger, best)

        # 4. Strategy Dispatch Loop (If no hit yet)
        if not best and strategy_obj:
            step_index = (
                attempt - 1
                if (filter_obj and filter_obj.preferred_model)
                else attempt
            )
            step = (
                strategy_obj.steps.filter(order=step_index)
                .select_related('failover_type')
                .first()
            )

            if not step:
                return False

            fail_type = step.failover_type.name.lower()

            if 'strict' in fail_type:
                return False

            elif 'local' in fail_type:
                if filter_obj and filter_obj.local_failover:
                    best = base_qs.filter(
                        id=filter_obj.local_failover_id
                    ).first()

            elif 'family' in fail_type:
                ref_family_id = None
                if filter_obj and filter_obj.preferred_model:
                    ref_family_id = (
                        filter_obj.preferred_model.ai_model.family_id
                    )

                if not ref_family_id:
                    v_match = None
                    if disc and getattr(disc, 'vector', None) is not None:
                        v_match = (
                            base_qs.annotate(
                                distance=CosineDistance(
                                    'ai_model__vector_node__embeddings',
                                    disc.vector,
                                )
                            )
                            .order_by('distance')
                            .first()
                        )
                    else:
                        v_match = base_qs.first()

                    if v_match:
                        ref_family_id = v_match.ai_model.family_id

                if ref_family_id:
                    qs_fam = base_qs.filter(ai_model__family_id=ref_family_id)
                    if disc and getattr(disc, 'vector', None) is not None:
                        best = (
                            qs_fam.annotate(
                                distance=CosineDistance(
                                    'ai_model__vector_node__embeddings',
                                    disc.vector,
                                )
                            )
                            .order_by(
                                'distance',
                                'aimodelpricing__input_cost_per_token',
                            )
                            .first()
                        )
                    else:
                        best = qs_fam.order_by(
                            'aimodelpricing__input_cost_per_token'
                        ).first()

            elif 'vector' in fail_type or not fail_type:
                if disc and getattr(disc, 'vector', None) is not None:
                    best = (
                        base_qs.annotate(
                            distance=CosineDistance(
                                'ai_model__vector_node__embeddings', disc.vector
                            )
                        )
                        .select_related('ai_model')
                        .order_by(
                            'distance', 'aimodelpricing__input_cost_per_token'
                        )
                        .first()
                    )
                else:
                    best = (
                        base_qs.select_related('ai_model')
                        .order_by('aimodelpricing__input_cost_per_token')
                        .first()
                    )

        # 5. Final Fallback
        if not best and not strategy_obj:
            if disc and getattr(disc, 'vector', None) is not None:
                best = (
                    base_qs.annotate(
                        distance=CosineDistance(
                            'ai_model__vector_node__embeddings', disc.vector
                        )
                    )
                    .select_related('ai_model')
                    .order_by(
                        'distance', 'aimodelpricing__input_cost_per_token'
                    )
                    .first()
                )
            else:
                best = (
                    base_qs.select_related('ai_model')
                    .order_by('aimodelpricing__input_cost_per_token')
                    .first()
                )

        if not best:
            return False

        ledger.ai_model_provider = best
        ledger.ai_model = best.ai_model
        return Hypothalamus._finalize_ledger(ledger, best)

    @staticmethod
    def _finalize_ledger(ledger, best):
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
        """Orchestrates the lock and state tracking, delegating all business logic."""
        running_status = SyncStatus.objects.get(id=SyncStatus.RUNNING)

        if AIModelSyncLog.objects.filter(status=running_status).exists():
            logger.warning('[Hypothalamus] Sync already running. Aborting.')
            return None

        sync_log = AIModelSyncLog.objects.create(status=running_status)

        # The strictly necessary state-machine wrapper. No business logic lives here.
        try:
            cls._execute_sync_pipeline(sync_log, use_local_cache, force_rebuild)
        except Exception as exc:
            logger.exception('[Hypothalamus] Fatal pipeline crash.')
            sync_log.status = SyncStatus.objects.get(id=SyncStatus.FAILED)
            sync_log.error_message = str(exc)
        finally:
            sync_log.save()

        return sync_log

    @classmethod
    def _execute_sync_pipeline(
        cls,
        sync_log: AIModelSyncLog,
        use_local_cache: bool,
        force_rebuild: bool,
    ) -> None:
        """The core ETL pipeline. Fails fast if data is unretrievable."""

        logger.info('[Hypothalamus] Execute Pipeline')
        catalog = cls._fetch_litellm_catalog(use_local_cache)
        if not catalog:
            raise RuntimeError('Catalog fetch returned empty or failed.')

        active_keys, flagged_models = cls._process_litellm_catalog(
            catalog, sync_log
        )
        cls._deactivate_stale_models(active_keys, sync_log)

        enriched_ids = cls.enrich_model_semantics_from_openrouter(
            use_local_cache=use_local_cache, force_rebuild=force_rebuild
        )
        flagged_models.update(enriched_ids)

        if force_rebuild:
            flagged_models.update(
                set(AIModel.objects.values_list('id', flat=True))
            )

        logger.info('[Hypothalamus] Sync Ollama.')
        cls._sync_local_ollama(sync_log)
        sync_log.status = SyncStatus.objects.get(id=SyncStatus.SUCCESS)

        if flagged_models:
            cls._trigger_vector_generation(flagged_models)

    @classmethod
    def _fetch_litellm_catalog(cls, use_local_cache: bool) -> dict:
        """Handles network/cache retrieval with surgical, localized exception catching."""
        cache, _ = LiteLLMCache.objects.get_or_create(id=1)

        if use_local_cache and cache.cached_catalog:
            logger.info('[Hypothalamus] Using local LiteLLM cache.')
            return cache.cached_catalog

        logger.info('[Hypothalamus] Fetching LiteLLM catalog from network...')

        try:
            response = requests.get(LITELLM_CATALOG_URL, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(
                f'[Hypothalamus] Network failure fetching catalog: {e}'
            )
            return {}

        try:
            catalog = response.json()
        except ValueError as e:
            logger.error(f'[Hypothalamus] Failed to parse catalog JSON: {e}')
            return {}

        cache.cached_catalog = catalog
        cache.save(update_fields=['cached_catalog'])
        return catalog

    @classmethod
    def _process_litellm_catalog(
        cls, catalog: dict, sync_log: AIModelSyncLog
    ) -> tuple[set, set]:
        """Iterates the raw dictionary and maps it to the database models."""
        active_provider_keys = set()
        models_flagged_for_vector_update = set()

        counter = 0
        catalog_size = len(catalog)
        with transaction.atomic():
            for raw_key, data in catalog.items():
                counter += 1
                logger.info(
                    f'Processing model {counter}/{catalog_size}: {raw_key}'
                )
                if raw_key in CATALOG_SKIP_KEYS:
                    continue

                active_provider_keys.add(raw_key)

                provider = cls._ensure_provider(data)
                mode = cls._ensure_mode(data)
                ai_model, model_created = cls._ensure_ai_model(raw_key, data)

                if model_created:
                    sync_log.models_added += 1
                    models_flagged_for_vector_update.add(ai_model.id)

                model_provider = cls._ensure_model_provider(
                    raw_key, ai_model, provider, mode, data
                )

                if cls._update_pricing(model_provider, data):
                    sync_log.prices_updated += 1

        return active_provider_keys, models_flagged_for_vector_update

    @classmethod
    def _deactivate_stale_models(
        cls, active_keys: set, sync_log: AIModelSyncLog
    ) -> None:
        """Sweeps and removes models that are no longer in the upstream catalog."""
        dead = AIModelPricing.objects.filter(
            is_current=True, is_active=True
        ).exclude(model_provider__provider_unique_model_id__in=active_keys)
        sync_log.models_deactivated = dead.count()
        dead.update(is_active=False)

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

    @classmethod
    def _ensure_ai_model(cls, raw_key: str, data: dict) -> tuple[AIModel, bool]:
        model_name = raw_key.split('/')[-1] if '/' in raw_key else raw_key
        context_length = (
            data.get('max_input_tokens') or data.get('max_tokens') or 4096
        )

        # 1. Route through the semantic parser and guarantee a Description is generated
        ai_model, created = cls._get_or_create_enriched_model(
            raw_slug=raw_key,
            display_name=model_name,
            context_length=context_length,
        )

        # 2. Retain the LiteLLM-specific capability flags
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

    @classmethod
    def _get_or_create_enriched_model(
        cls, raw_slug: str, display_name: str, context_length: int
    ) -> tuple[AIModel, bool]:
        """Centralized factory that runs the semantic parser and UPDATES existing models."""
        parsed = parse_model_string(raw_slug)

        ai_model, created = AIModel.objects.get_or_create(
            name=display_name, defaults={'context_length': context_length}
        )
        needs_save = False
        update_fields = []
        if parsed.parameter_size and not ai_model.parameter_size:
            ai_model.parameter_size = parsed.parameter_size
            update_fields.append('parameter_size')
            needs_save = True
        if parsed.family and not ai_model.family_id:
            ai_model.family = parsed.family
            update_fields.append('family')
            needs_save = True
        if parsed.version and not ai_model.version_id:
            ai_model.version = parsed.version
            update_fields.append('version')
            needs_save = True
        if parsed.creator and not ai_model.creator_id:
            ai_model.creator = parsed.creator
            update_fields.append('creator')
            needs_save = True
        if needs_save:
            ai_model.save(update_fields=update_fields)
        if parsed.roles:
            ai_model.roles.add(*parsed.roles)
        if parsed.quantizations:
            ai_model.quantizations.add(*parsed.quantizations)
        current_desc = ai_model.aimodeldescription_set.first()
        if not current_desc:
            current_desc = AIModelDescription.objects.create(is_current=True)
            current_desc.ai_models.add(ai_model)
        if parsed.tags:
            current_desc.tags.add(*parsed.tags)
        if parsed.family:
            current_desc.families.add(parsed.family)
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

        # THE FIX: If the price matches BUT it was deactivated by the stale sweep, resurrect it!
        if (
            current
            and current.input_cost_per_token == in_cost
            and current.output_cost_per_token == out_cost
        ):
            if not current.is_active:
                current.is_active = True
                current.save(update_fields=['is_active'])
                return True  # We did make an update
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
        """Main orchestrator for OpenRouter data ingestion and semantic updates."""
        logger.info('[Hypothalamus] Enriching OpenRouter authoritative data...')
        modified_model_ids = set()

        payload = cls._fetch_openrouter_catalog(use_local_cache)
        openrouter_models = payload.get('data', [])

        if not openrouter_models:
            return modified_model_ids

        or_llm_provider, _ = LLMProvider.objects.get_or_create(
            key='openrouter', defaults={'name': 'OpenRouter'}
        )
        chat_mode, _ = AIMode.objects.get_or_create(name=CHAT_MODE)

        # --- THE HEALING MECHANIC ---
        if force_rebuild:
            cls._rehabilitate_openrouter_models(or_llm_provider)

        length = len(openrouter_models)

        try:
            with transaction.atomic():
                for counter, or_data in enumerate(openrouter_models, start=1):
                    if counter % 50 == 0:
                        logger.info(
                            f'[Hypothalamus] Processing OpenRouter model {counter} of {length}'
                        )

                    modified_id = cls._process_openrouter_model(
                        or_data, or_llm_provider, chat_mode, force_rebuild
                    )
                    if modified_id:
                        modified_model_ids.add(modified_id)

        except Exception:
            logger.exception(
                '[Hypothalamus] OpenRouter semantic enrichment failed during processing loop.'
            )

        return modified_model_ids

    @classmethod
    def _fetch_openrouter_catalog(cls, use_local_cache: bool) -> dict:
        """Handles network/cache retrieval with strict boundary exceptions."""
        if use_local_cache:
            latest_cache = AIModelDescriptionCache.objects.order_by(
                '-created'
            ).first()
            if latest_cache and latest_cache.cached_library:
                logger.info('[Hypothalamus] Using local OpenRouter cache.')
                return latest_cache.cached_library

        logger.info('[Hypothalamus] Fetching OpenRouter models from network...')

        try:
            response = requests.get(OPENROUTER_MODELS_URL, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(
                f'[Hypothalamus] Network failure fetching OpenRouter catalog: {e}'
            )
            return {}

        try:
            payload = response.json()
        except ValueError as e:
            logger.error(f'[Hypothalamus] Failed to parse OpenRouter JSON: {e}')
            return {}

        AIModelDescriptionCache.objects.create(cached_library=payload)
        return payload

    @classmethod
    def _rehabilitate_openrouter_models(cls, provider: LLMProvider) -> None:
        """Wipes the scar tissue (disabled_capabilities) for a fresh start on force rebuilds."""
        logger.info(
            '[Hypothalamus] Force rebuild active: Rehabilitating OpenRouter models.'
        )
        providers = AIModelProvider.objects.filter(provider=provider)
        for p in providers:
            p.disabled_capabilities.clear()

    @classmethod
    def _process_openrouter_model(
        cls,
        or_data: dict,
        provider: LLMProvider,
        mode: AIMode,
        force_rebuild: bool,
    ) -> Optional[int]:
        """Handles the ingestion of a single model's routing, capability, and pricing data."""
        stripped_id = or_data['id']
        provider_unique_id = f'openrouter/{stripped_id}'
        display_name = or_data.get('name', stripped_id)
        context_length = or_data.get('context_length', 4096)

        # 1. Ensure AIModel via our new Semantic Parser
        ai_model, _ = cls._get_or_create_enriched_model(
            raw_slug=provider_unique_id,
            display_name=display_name,
            context_length=context_length,
        )

        # 2. Optimistic Inheritance (No string-matching guesswork!)
        if ':' in stripped_id:
            base_id = stripped_id.split(':')[0]
            base_provider = (
                AIModelProvider.objects.filter(
                    provider_unique_model_id=f'openrouter/{base_id}'
                )
                .select_related('ai_model')
                .first()
            )

            if base_provider and base_provider.ai_model:
                base_caps = base_provider.ai_model.capabilities.all()
                if base_caps.exists():
                    ai_model.capabilities.add(*base_caps)

        # 3. Ensure Provider Record
        model_provider, _ = AIModelProvider.objects.update_or_create(
            provider_unique_model_id=provider_unique_id,
            defaults={
                'ai_model': ai_model,
                'provider': provider,
                'mode': mode,
                'max_input_tokens': or_data.get('context_length'),
            },
        )

        # 4. Enforce Pricing
        or_pricing = or_data.get('pricing', {})
        mocked_price_data = {
            'input_cost_per_token': _dec('prompt', or_pricing),
            'output_cost_per_token': _dec('completion', or_pricing),
        }
        cls._update_pricing(model_provider, mocked_price_data)

        # 5. Semantic Enrichment
        return cls._enrich_openrouter_semantics(
            ai_model, or_data, force_rebuild
        )

    @classmethod
    def _enrich_openrouter_semantics(
        cls, ai_model: AIModel, or_data: dict, force_rebuild: bool
    ) -> Optional[UUID]:
        new_desc = or_data.get('description', '')
        arch = or_data.get('architecture', {})

        extracted_tags = []
        if arch.get('modality'):
            extracted_tags.append(f'modality:{arch["modality"]}')
        if arch.get('instruct_type'):
            extracted_tags.append(f'instruct:{arch["instruct_type"]}')

        current_desc_obj = ai_model.aimodeldescription_set.first()

        is_different = (not current_desc_obj) or (
            current_desc_obj.description != new_desc
        )

        if new_desc and (is_different or force_rebuild):
            if not current_desc_obj:
                current_desc_obj = AIModelDescription.objects.create(
                    description=new_desc, is_current=True
                )
                current_desc_obj.ai_models.add(ai_model)
            else:
                current_desc_obj.description = new_desc
                current_desc_obj.save(update_fields=['description'])

            for tag_string in extracted_tags:
                tag_obj, _ = AIModelTags.objects.get_or_create(name=tag_string)
                current_desc_obj.tags.add(tag_obj)

            return ai_model.id

        return None

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

    @classmethod
    def _sync_local_ollama(cls, sync_log: AIModelSyncLog) -> None:
        """Mirrors the local hard drive state using the provider's is_enabled flag."""
        logger.info('[Hypothalamus] Syncing local Ollama instance...')

        ollama_provider, _ = LLMProvider.objects.get_or_create(
            key='ollama',
            defaults={'name': 'Ollama', 'base_url': 'http://localhost:11434'},
        )

        if not ollama_provider.base_url:
            logger.warning(
                '[Hypothalamus] Ollama provider missing base_url. Skipping.'
            )
            return

        # 1. Discover what is physically on the hard drive
        installed_models = cls._fetch_ollama_tags(ollama_provider.base_url)
        installed_names = {
            m.get('name') for m in installed_models if m.get('name')
        }
        installed_provider_ids = set()

        chat_mode, _ = AIMode.objects.get_or_create(name=CHAT_MODE)

        with transaction.atomic():
            # 2. Activate what is on the hard drive
            for model_name in installed_names:
                provider_id = f'ollama/{model_name}'
                installed_provider_ids.add(provider_id)
                cls._process_installed_ollama_model(
                    model_name, provider_id, ollama_provider, chat_mode
                )

            # 3. Bench what is NOT on the hard drive (The Ghost Models)
            dead_ollama_providers = AIModelProvider.objects.filter(
                provider=ollama_provider,
                is_enabled=True,  # Only grab ones that think they are active
            ).exclude(provider_unique_model_id__in=installed_provider_ids)

            deactivated_count = dead_ollama_providers.count()
            if deactivated_count > 0:
                logger.info(
                    f'[Hypothalamus] Benched {deactivated_count} missing local Ollama models.'
                )
                dead_ollama_providers.update(is_enabled=False)

    @classmethod
    def _process_installed_ollama_model(
        cls,
        model_name: str,
        provider_unique_id: str,
        provider: LLMProvider,
        mode: AIMode,
    ) -> None:
        """Registers and enables a verified local model into the routing pool."""

        # --- THE INJECTION ---
        ai_model, _ = cls._get_or_create_enriched_model(
            raw_slug=provider_unique_id,
            # e.g. ollama/llama3.1:8b-instruct-q4_K_M
            display_name=model_name,
            context_length=8192,  # Safe default for local models
        )

        model_provider, _ = AIModelProvider.objects.update_or_create(
            provider_unique_model_id=provider_unique_id,
            defaults={
                'ai_model': ai_model,
                'provider': provider,
                'mode': mode,
                'is_enabled': True,
            },
        )

        # Ollama is always $0.00. Enforce that reality.
        mocked_free_pricing = {
            'input_cost_per_token': Decimal('0.0'),
            'output_cost_per_token': Decimal('0.0'),
        }
        cls._update_pricing(model_provider, mocked_free_pricing)

    @classmethod
    def _fetch_ollama_tags(cls, base_url: str) -> list:
        """Safely fetches the list of installed models from the local Ollama API."""
        try:
            url = f'{base_url.rstrip("/")}/api/tags'
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return response.json().get('models', [])
        except (requests.RequestException, ValueError) as e:
            logger.warning(
                f'[Hypothalamus] Could not reach local Ollama at {base_url}: {e}'
            )
            return []
