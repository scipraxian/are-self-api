import logging

import requests as http_requests
from asgiref.sync import async_to_sync
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Acetylcholine

from .models import (
    AIMode,
    AIModel,
    AIModelCategory,
    AIModelDescription,
    AIModelFamily,
    AIModelPricing,
    AIModelProvider,
    AIModelProviderUsageRecord,
    AIModelRating,
    AIModelSelectionFilter,
    AIModelSyncLog,
    FailoverStrategy,
    FailoverType,
    LLMProvider,
    SyncStatus,
)
from .serializers import (
    AIModeSerializer,
    AIModelCategorySerializer,
    AIModelDescriptionSerializer,
    AIModelFamilySerializer,
    AIModelPricingSerializer,
    AIModelProviderSerializer,
    AIModelProviderUsageRecordSerializer,
    AIModelRatingSerializer,
    AIModelSelectionFilterSerializer,
    AIModelSerializer,
    AIModelSyncLogSerializer,
    FailoverStrategySerializer,
    FailoverTypeSerializer,
    LLMProviderSerializer,
    SyncStatusSerializer,
)

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = 'http://localhost:11434'
OLLAMA_PULL_TIMEOUT = 600
OLLAMA_DELETE_TIMEOUT = 30
OLLAMA_PROVIDER_KEY = 'ollama'


def get_ollama_provider() -> LLMProvider:
    """Returns the Ollama LLMProvider instance."""
    return LLMProvider.objects.get(key=OLLAMA_PROVIDER_KEY)


class LLMProviderViewSet(viewsets.ModelViewSet):
    queryset = LLMProvider.objects.all()
    serializer_class = LLMProviderSerializer


class AIModelCategoryViewSet(viewsets.ModelViewSet):
    queryset = AIModelCategory.objects.all()
    serializer_class = AIModelCategorySerializer


class AIModeViewSet(viewsets.ModelViewSet):
    queryset = AIMode.objects.all()
    serializer_class = AIModeSerializer


class AIModelFamilyViewSet(viewsets.ModelViewSet):
    queryset = AIModelFamily.objects.all()
    serializer_class = AIModelFamilySerializer


class AIModelViewSet(viewsets.ModelViewSet):
    queryset = AIModel.objects.all()
    serializer_class = AIModelSerializer

    @action(detail=True, methods=['post'])
    def pull(self, request, pk=None):
        """Pull a model into Ollama and register the provider."""
        ai_model = self.get_object()
        model_name = ai_model.name

        try:
            resp = http_requests.post(
                f'{OLLAMA_BASE_URL}/api/pull',
                json={'name': model_name, 'stream': False},
                timeout=OLLAMA_PULL_TIMEOUT,
            )
            resp.raise_for_status()
        except http_requests.RequestException as exc:
            logger.error(
                '[Hypothalamus] Ollama pull failed for %s: %s',
                model_name,
                exc,
            )
            return Response(
                {'error': f'Ollama pull failed: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        ollama_provider = get_ollama_provider()

        # Determine mode: embedding if model has an embedding role
        embedding_role = ai_model.roles.filter(name='embedding').exists()
        mode_name = 'embedding' if embedding_role else 'chat'
        mode, _ = AIMode.objects.get_or_create(name=mode_name)

        provider_model_id = f'ollama/{model_name}'
        model_provider, _ = AIModelProvider.objects.get_or_create(
            provider_unique_model_id=provider_model_id,
            defaults={
                'ai_model': ai_model,
                'provider': ollama_provider,
                'mode': mode,
            },
        )
        model_provider.is_enabled = True
        model_provider.save(update_fields=['is_enabled'])

        AIModelPricing.objects.get_or_create(
            model_provider=model_provider,
            is_current=True,
            is_active=True,
            defaults={
                'input_cost_per_token': 0,
                'output_cost_per_token': 0,
            },
        )

        async_to_sync(fire_neurotransmitter)(
            Acetylcholine(
                receptor_class='AIModel',
                dendrite_id=str(ai_model.pk),
                activity='updated',
                vesicle={'action': 'pulled', 'model_name': model_name},
            )
        )

        serializer = self.get_serializer(ai_model)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def remove(self, request, pk=None):
        """Remove a model from Ollama and disable the provider."""
        ai_model = self.get_object()
        model_name = ai_model.name

        try:
            resp = http_requests.delete(
                f'{OLLAMA_BASE_URL}/api/delete',
                json={'name': model_name},
                timeout=OLLAMA_DELETE_TIMEOUT,
            )
            resp.raise_for_status()
        except http_requests.RequestException as exc:
            logger.error(
                '[Hypothalamus] Ollama remove failed for %s: %s',
                model_name,
                exc,
            )
            return Response(
                {'error': f'Ollama remove failed: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        ollama_provider = get_ollama_provider()
        AIModelProvider.objects.filter(
            ai_model=ai_model,
            provider=ollama_provider,
        ).update(is_enabled=False)

        async_to_sync(fire_neurotransmitter)(
            Acetylcholine(
                receptor_class='AIModel',
                dendrite_id=str(ai_model.pk),
                activity='updated',
                vesicle={'action': 'removed', 'model_name': model_name},
            )
        )

        serializer = self.get_serializer(ai_model)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='toggle_enabled')
    def toggle_enabled(self, request, pk=None):
        """Toggle the AIModel.enabled flag."""
        ai_model = self.get_object()
        ai_model.enabled = not ai_model.enabled
        ai_model.save(update_fields=['enabled'])
        serializer = self.get_serializer(ai_model)
        return Response(serializer.data)


class AIModelProviderViewSet(viewsets.ModelViewSet):
    queryset = AIModelProvider.objects.all()
    serializer_class = AIModelProviderSerializer

    @action(detail=True, methods=['post'], url_path='reset_circuit_breaker')
    def reset_circuit_breaker(self, request, pk=None):
        """Reset the circuit breaker on this provider."""
        provider = self.get_object()
        provider.reset_circuit_breaker()
        serializer = self.get_serializer(provider)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='toggle_enabled')
    def toggle_enabled(self, request, pk=None):
        """Toggle the AIModelProvider.is_enabled flag."""
        provider = self.get_object()
        provider.is_enabled = not provider.is_enabled
        provider.save(update_fields=['is_enabled'])
        serializer = self.get_serializer(provider)
        return Response(serializer.data)


class AIModelPricingViewSet(viewsets.ModelViewSet):
    queryset = AIModelPricing.objects.all()
    serializer_class = AIModelPricingSerializer


class AIModelProviderUsageRecordViewSet(viewsets.ModelViewSet):
    queryset = AIModelProviderUsageRecord.objects.all()
    serializer_class = AIModelProviderUsageRecordSerializer


class SyncStatusViewSet(viewsets.ModelViewSet):
    queryset = SyncStatus.objects.all()
    serializer_class = SyncStatusSerializer


class AIModelSyncLogViewSet(viewsets.ModelViewSet):
    queryset = AIModelSyncLog.objects.all()
    serializer_class = AIModelSyncLogSerializer


class AIModelRatingViewSet(viewsets.ModelViewSet):
    queryset = AIModelRating.objects.all()
    serializer_class = AIModelRatingSerializer


class FailoverTypeViewSet(viewsets.ModelViewSet):
    queryset = FailoverType.objects.all()
    serializer_class = FailoverTypeSerializer


class FailoverStrategyViewSet(viewsets.ModelViewSet):
    queryset = FailoverStrategy.objects.all()
    serializer_class = FailoverStrategySerializer


class AIModelSelectionFilterViewSet(viewsets.ModelViewSet):
    queryset = AIModelSelectionFilter.objects.all()
    serializer_class = AIModelSelectionFilterSerializer


class AIModelDescriptionViewSet(viewsets.ModelViewSet):
    queryset = AIModelDescription.objects.all()
    serializer_class = AIModelDescriptionSerializer
