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
    AIModelPricing,
    AIModelProvider,
    AIModelSyncLog,
    LLMProvider,
    SyncStatus,
)
from hypothalamus.serializers import ModelSelection

LITELLM_CATALOG_URL = (
    'https://raw.githubusercontent.com/BerriAI/litellm/main'
    '/model_prices_and_context_window.json'
)
CATALOG_SKIP_KEYS = frozenset({'sample_spec'})
CHAT_MODE = 'chat'

logger = logging.getLogger(__name__)


def _dec(key: str, data: dict) -> Decimal:
    return Decimal(str(data.get(key) or 0.0))


class Hypothalamus:
    @staticmethod
    def pick_optimal_model(disc, payload_size: int) -> Optional[ModelSelection]:
        """
        Finds the closest mathematical match to the Persona, constrained by budget, context window, and API rate limits.
        """

        # Get budget constraint
        max_cost = (
            disc.budget.max_input_cost_per_token
            if hasattr(disc, 'budget')
            else 0
        )
        valid_provider_ids = [
            p.id
            for p in LLMProvider.objects.all()
            if not p.requires_api_key or p.has_active_key
        ]
        # THE CIRCUIT BREAKER FILTER:
        # Only allow models where reset_time is NULL, or the reset_time has already passed.
        breaker_filter = Q(rate_limit_reset_time__isnull=True) | Q(
            rate_limit_reset_time__lte=timezone.now()
        )

        # Base active filters
        filters = {
            'provider_id__in': valid_provider_ids,
            'mode__name': 'chat',
            'ai_model__enabled': True,
            'aimodelpricing__is_current': True,
            'aimodelpricing__is_active': True,
            'aimodelpricing__input_cost_per_token__lte': max_cost,
            'ai_model__context_length__gte': payload_size,
        }

        # Execute Vector Math routing
        best = (
            AIModelProvider.objects.filter(breaker_filter, **filters)
            .annotate(distance=CosineDistance('ai_model__vector', disc.vector))
            .select_related('ai_model')
            .order_by('distance', 'aimodelpricing__input_cost_per_token')
            .first()
        )

        if not best:
            return None

        # Return structured selection
        pricing = best.aimodelpricing_set.filter(is_current=True).first()
        cost = pricing.input_cost_per_token if pricing else 0

        # Assuming you have a ModelSelection dataclass or similar structure
        return ModelSelection(
            provider_model_id=best.provider_unique_model_id,
            ai_model_name=best.ai_model.name,
            distance=getattr(best, 'distance', 0.0),
            input_cost_per_token=cost,
            is_fallback=False,
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
