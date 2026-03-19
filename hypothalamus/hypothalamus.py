import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import requests
from django.db import transaction
from pgvector.django import CosineDistance

from hypothalamus.models import (
    AIMode,
    AIModel,
    AIModelPricing,
    AIModelProvider,
    AIModelSyncLog,
    LLMProvider,
    SyncStatus,
)
from identity.models import IdentityDisc

logger = logging.getLogger(__name__)

LITELLM_CATALOG_URL = (
    'https://raw.githubusercontent.com/BerriAI/litellm/main'
    '/model_prices_and_context_window.json'
)
FALLBACK_MODEL_ID = 'ollama/qwen2.5-coder:8b'
CATALOG_SKIP_KEYS = frozenset({'sample_spec'})
CHAT_MODE = 'chat'


@dataclass(frozen=True)
class ModelSelection:
    """The result of a Hypothalamus routing decision."""

    provider_model_id: str
    ai_model_name: str
    distance: float
    input_cost_per_token: Decimal
    is_fallback: bool = False

    @classmethod
    def fallback(cls) -> 'ModelSelection':
        return cls(
            provider_model_id=FALLBACK_MODEL_ID,
            ai_model_name=FALLBACK_MODEL_ID,
            distance=1.0,
            input_cost_per_token=Decimal('0'),
            is_fallback=True,
        )


@dataclass(frozen=True)
class SyncResult:
    """Summary of a catalog sync run."""

    models_added: int
    providers_added: int
    prices_updated: int
    models_deactivated: int
    status: str
    error: Optional[str] = None


def _dec(key: str, data: dict) -> Decimal:
    return Decimal(str(data.get(key) or 0.0))


class Hypothalamus:
    @staticmethod
    def pick_optimal_model(
        disc: IdentityDisc,
        payload_size: int,
        require_function_calling: bool = False,
        require_vision: bool = False,
    ) -> ModelSelection:
        """
        Selects the best-fit AIModelProvider for a given IdentityDisc and payload.
        Uses cosine distance between the disc's vector and each candidate model's
        vector, filtered by budget, context window, mode, and capability flags.
        """
        if not disc.vector:
            logger.warning(
                '[Hypothalamus] Disc %s has no vector. Using fallback.', disc.id
            )
            return ModelSelection.fallback()

        max_cost = (
            disc.budget.max_input_cost_per_token
            if disc.budget
            else Decimal('0.0')
        )

        filters = {
            'mode__name': CHAT_MODE,
            'aimodelpricing__is_current': True,
            'aimodelpricing__is_active': True,
            'aimodelpricing__input_cost_per_token__lte': max_cost,
            'ai_model__context_length__gte': payload_size,
        }
        if require_function_calling:
            filters['ai_model__supports_function_calling'] = True
        if require_vision:
            filters['ai_model__supports_vision'] = True

        best = (
            AIModelProvider.objects.filter(**filters)
            .annotate(distance=CosineDistance('ai_model__vector', disc.vector))
            .select_related('ai_model', 'aimodelpricing')
            .order_by('distance')
            .values(
                'provider_unique_model_id',
                'ai_model__name',
                'distance',
                'aimodelpricing__input_cost_per_token',
            )
            .first()
        )

        if not best:
            logger.warning(
                '[Hypothalamus] No model fit budget=%.15f context=%d for disc %s.',
                max_cost,
                payload_size,
                disc.id,
            )
            return ModelSelection.fallback()

        return ModelSelection(
            provider_model_id=best['provider_unique_model_id'],
            ai_model_name=best['ai_model__name'],
            distance=best['distance'],
            input_cost_per_token=best['aimodelpricing__input_cost_per_token'],
        )

    @classmethod
    def sync_catalog(cls) -> Optional[AIModelSyncLog]:
        """
        Pulls the LiteLLM model universe, updates pricing ledgers,
        and tombstones dead models. Designed to run via Celery Beat daily.
        """
        running_status = SyncStatus.objects.get(id=SyncStatus.RUNNING)

        if AIModelSyncLog.objects.filter(status=running_status).exists():
            logger.warning('[Hypothalamus] Sync already running. Aborting.')
            return None

        sync_log = AIModelSyncLog.objects.create(status=running_status)
        active_provider_keys: set[str] = set()

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

                    model_provider = cls._ensure_model_provider(
                        raw_key, ai_model, provider, mode, data
                    )
                    price_updated = cls._update_pricing(model_provider, data)
                    if price_updated:
                        sync_log.prices_updated += 1

                # Tombstone dead entries inside the same transaction
                dead = AIModelPricing.objects.filter(
                    is_current=True, is_active=True
                ).exclude(
                    model_provider__provider_unique_model_id__in=active_provider_keys
                )
                sync_log.models_deactivated = dead.count()
                dead.update(is_active=False)

            sync_log.status = SyncStatus.objects.get(id=SyncStatus.SUCCESS)

        except Exception as exc:
            logger.exception('[Hypothalamus] Sync failed.')
            sync_log.status = SyncStatus.objects.get(id=SyncStatus.FAILED)
            sync_log.error_message = str(exc)

        finally:
            sync_log.save()
            if (
                sync_log.status_id == SyncStatus.SUCCESS
                and sync_log.models_added > 0
            ):
                cls._trigger_vector_generation()

        return sync_log

    # ------------------------------------------------------------------ #
    #  Private helpers — one responsibility each                          #
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
    def _ensure_ai_model(raw_key: str, data: dict):
        model_name = raw_key.split('/')[-1] if '/' in raw_key else raw_key
        return AIModel.objects.get_or_create(
            name=model_name,
            defaults={
                'context_length': (
                    data.get('max_input_tokens')
                    or data.get('max_tokens')
                    or 4096
                ),
                'supports_vision': data.get('supports_vision', False),
                'supports_function_calling': data.get(
                    'supports_function_calling', False
                ),
                # New fields from sample_spec:
                'supports_parallel_function_calling': data.get(
                    'supports_parallel_function_calling', False
                ),
                'supports_response_schema': data.get(
                    'supports_response_schema', False
                ),
                'supports_system_messages': data.get(
                    'supports_system_messages', True
                ),
                'supports_prompt_caching': data.get(
                    'supports_prompt_caching', False
                ),
                'supports_reasoning': data.get('supports_reasoning', False),
                'supports_audio_input': data.get('supports_audio_input', False),
                'supports_audio_output': data.get(
                    'supports_audio_output', False
                ),
                'supports_web_search': data.get('supports_web_search', False),
            },
        )

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
        """
        Creates a new pricing record if costs have changed. Returns True if
        a change was detected and a new record was written.
        """

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
            return False  # No change

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
    def _trigger_vector_generation(cls):
        unmapped = AIModel.objects.filter(vector__isnull=True)
        logger.info(
            '[Hypothalamus] Vectorizing %d new models.', unmapped.count()
        )
        for model in unmapped:
            model.update_vector()
