import logging
import re

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
    AIModelCapabilities,
    AIModelCategory,
    AIModelCreator,
    AIModelDescription,
    AIModelFamily,
    AIModelPricing,
    AIModelProvider,
    AIModelProviderUsageRecord,
    AIModelQuantization,
    AIModelRating,
    AIModelRole,
    AIModelSelectionFilter,
    AIModelSyncLog,
    AIModelTags,
    FailoverStrategy,
    FailoverType,
    LLMProvider,
    SyncStatus,
)
from .parsing_tools.llm_provider_parser.model_semantic_parser import (
    parse_model_string,
)
from .serializers import (
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
    AIModeSerializer,
    FailoverStrategySerializer,
    FailoverTypeSerializer,
    LLMProviderSerializer,
    SyncStatusSerializer,
)

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = 'http://localhost:11434'
OLLAMA_TAGS_TIMEOUT = 10
OLLAMA_PULL_TIMEOUT = 600
OLLAMA_DELETE_TIMEOUT = 30
OLLAMA_PROVIDER_KEY = 'ollama'
OLLAMA_LIBRARY_URL = 'https://ollama.com/library'
OLLAMA_LIBRARY_TIMEOUT = 30
DEFAULT_CONTEXT_LENGTH = 131072
EMBED_KEYWORD = 'embed'

CAPABILITY_BADGE_MAP = {
    'tools': 'function_calling',
    'vision': 'vision',
    'thinking': 'reasoning',
}


def get_ollama_provider() -> LLMProvider:
    """Returns the Ollama LLMProvider instance."""
    return LLMProvider.objects.get(key=OLLAMA_PROVIDER_KEY)


def parse_parameter_size(raw: str) -> float | None:
    """Parse a parameter size string like '27.2B' into a float."""
    if not raw:
        return None
    cleaned = raw.strip().upper().rstrip('B')
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def match_family_by_slug(slug: str) -> AIModelFamily | None:
    """Match a lowercase family string against AIModelFamily.slug values."""
    slug_lower = slug.lower()
    try:
        return AIModelFamily.objects.get(slug=slug_lower)
    except AIModelFamily.DoesNotExist:
        return None


LINK_RE = re.compile(
    r'<a\s[^>]*href="/library/([a-zA-Z0-9._-]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)
DESC_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.DOTALL)
SPAN_RE = re.compile(r'<span[^>]*>(.*?)</span>', re.DOTALL)
SIZE_RE = re.compile(r'^\d+(\.\d+)?[bm]$', re.IGNORECASE)
BADGE_VALUES = frozenset(
    {'tools', 'vision', 'thinking', 'embedding', 'cloud'}
)


def scrape_ollama_library(html_text: str) -> list[dict]:
    """Extract model entries from ollama.com/library HTML.

    Returns list of dicts with keys: name, description, badges, sizes.
    No classes, no state tracking. Just regex.
    """
    results = []
    for link_match in LINK_RE.finditer(html_text):
        slug = link_match.group(1)
        inner = link_match.group(2)

        desc_match = DESC_RE.search(inner)
        description = desc_match.group(1).strip() if desc_match else ''

        badges = []
        sizes = []
        for span_match in SPAN_RE.finditer(inner):
            text = span_match.group(1).strip().lower()
            if text in BADGE_VALUES:
                badges.append(text)
            elif SIZE_RE.match(text):
                sizes.append(text)

        results.append({
            'name': slug,
            'description': description,
            'badges': badges,
            'sizes': sizes,
        })

    return results


def _enrich_from_parser(ai_model: AIModel, model_name: str) -> None:
    """Apply parsed semantic data to an AIModel if fields are empty."""
    parsed = parse_model_string(model_name)
    if not parsed.success:
        return

    if not ai_model.family_id and parsed.family:
        try:
            family = AIModelFamily.objects.get(
                name__iexact=parsed.family
            )
            ai_model.family = family
            ai_model.save(update_fields=['family'])
        except AIModelFamily.DoesNotExist:
            pass

    if not ai_model.creator_id and parsed.creator:
        try:
            creator = AIModelCreator.objects.get(
                name__iexact=parsed.creator
            )
            ai_model.creator = creator
            ai_model.save(update_fields=['creator'])
        except AIModelCreator.DoesNotExist:
            pass

    if not ai_model.parameter_size and parsed.parameter_size:
        size = parse_parameter_size(parsed.parameter_size)
        if size:
            ai_model.parameter_size = size
            ai_model.save(update_fields=['parameter_size'])

    for role_name in parsed.roles:
        try:
            role = AIModelRole.objects.get(name__iexact=role_name)
            ai_model.roles.add(role)
        except AIModelRole.DoesNotExist:
            pass

    for quant_name in parsed.quantizations:
        try:
            quant = AIModelQuantization.objects.get(
                name__iexact=quant_name
            )
            ai_model.quantizations.add(quant)
        except AIModelQuantization.DoesNotExist:
            pass


def _process_catalog_entry(entry: dict) -> bool:
    """Process a single scraped catalog entry. Returns True if new AIModel created."""
    model_name = entry['name']
    description_text = entry.get('description', '')
    badges = entry.get('badges', [])
    sizes = entry.get('sizes', [])

    ai_model, created = AIModel.objects.get_or_create(
        name=model_name,
        defaults={
            'context_length': DEFAULT_CONTEXT_LENGTH,
            'enabled': True,
        },
    )

    _enrich_from_parser(ai_model, model_name)

    for badge in badges:
        cap_name = CAPABILITY_BADGE_MAP.get(badge)
        if cap_name:
            cap, _ = AIModelCapabilities.objects.get_or_create(name=cap_name)
            ai_model.capabilities.add(cap)

    existing_desc = AIModelDescription.objects.filter(
        ai_models=ai_model, is_current=True
    ).first()

    if existing_desc:
        if description_text:
            existing_desc.description = description_text
            existing_desc.save(update_fields=['description'])
        desc_obj = existing_desc
    else:
        desc_obj = AIModelDescription.objects.create(
            description=description_text,
            is_current=True,
        )
        desc_obj.ai_models.add(ai_model)

    if ai_model.family:
        desc_obj.families.add(ai_model.family)

    for badge in badges:
        tag, _ = AIModelTags.objects.get_or_create(name=badge)
        desc_obj.tags.add(tag)

    for size_label in sizes:
        tag_name = f'size:{size_label.lower()}'
        tag, _ = AIModelTags.objects.get_or_create(name=tag_name)
        desc_obj.tags.add(tag)

    return created


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

    @action(detail=False, methods=['post'], url_path='sync_local')
    def sync_local(self, request):
        """Sync the local Ollama instance into the model catalog."""
        try:
            resp = http_requests.get(
                f'{OLLAMA_BASE_URL}/api/tags',
                timeout=OLLAMA_TAGS_TIMEOUT,
            )
            resp.raise_for_status()
        except http_requests.ConnectionError:
            return Response(
                {'error': 'Ollama is not running. Start Ollama and try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except http_requests.RequestException as exc:
            logger.error(
                '[Hypothalamus] sync_local failed to reach Ollama: %s', exc
            )
            return Response(
                {'error': 'Ollama is not running. Start Ollama and try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        installed_models = resp.json().get('models', [])
        ollama_provider = get_ollama_provider()
        synced_names = []
        installed_provider_ids = set()

        for model_data in installed_models:
            raw_name = model_data.get('name', '')
            if not raw_name:
                continue

            # Run through the parser — cleans :latest, extracts family/creator/size/roles
            parsed = parse_model_string(f'ollama/{raw_name}')

            # Derive clean name: strip :latest (parser does this), but keep real tags like :3b
            clean_name = raw_name
            if clean_name.endswith(':latest'):
                clean_name = clean_name[:-7]

            provider_unique_id = f'ollama/{clean_name}'
            installed_provider_ids.add(provider_unique_id)

            ai_model, _ = AIModel.objects.get_or_create(
                name=clean_name,
                defaults={
                    'context_length': DEFAULT_CONTEXT_LENGTH,
                    'enabled': True,
                },
            )

            # Enrich from parser (family, creator, size, roles, quantizations)
            _enrich_from_parser(ai_model, f'ollama/{raw_name}')

            # Also apply parameter_size from Ollama's own details if parser didn't get it
            details = model_data.get('details', {})
            if not ai_model.parameter_size:
                param_size = parse_parameter_size(
                    details.get('parameter_size', '')
                )
                if param_size:
                    ai_model.parameter_size = param_size
                    ai_model.save(update_fields=['parameter_size'])

            is_embedding = EMBED_KEYWORD in clean_name.lower()
            mode_name = 'embedding' if is_embedding else 'chat'
            mode, _ = AIMode.objects.get_or_create(name=mode_name)

            model_provider, _ = AIModelProvider.objects.update_or_create(
                provider_unique_model_id=provider_unique_id,
                defaults={
                    'ai_model': ai_model,
                    'provider': ollama_provider,
                    'mode': mode,
                    'is_enabled': True,
                },
            )

            AIModelPricing.objects.get_or_create(
                model_provider=model_provider,
                is_current=True,
                is_active=True,
                defaults={
                    'input_cost_per_token': 0,
                    'output_cost_per_token': 0,
                },
            )

            synced_names.append(clean_name)

        disabled_count = AIModelProvider.objects.filter(
            provider=ollama_provider,
            is_enabled=True,
        ).exclude(
            provider_unique_model_id__in=installed_provider_ids
        ).update(is_enabled=False)

        async_to_sync(fire_neurotransmitter)(
            Acetylcholine(
                receptor_class='AIModel',
                dendrite_id='sync_local',
                activity='updated',
                vesicle={'action': 'sync_local'},
            )
        )

        logger.info(
            '[Hypothalamus] sync_local complete. Synced: %d, Disabled: %d',
            len(synced_names),
            disabled_count,
        )

        return Response({
            'synced': len(synced_names),
            'disabled': disabled_count,
            'models': synced_names,
        })

    @action(detail=False, methods=['post'], url_path='fetch_catalog')
    def fetch_catalog(self, request):
        """Scrape ollama.com/library and enrich the model catalog."""
        try:
            resp = http_requests.get(
                OLLAMA_LIBRARY_URL,
                timeout=OLLAMA_LIBRARY_TIMEOUT,
            )
            resp.raise_for_status()
        except http_requests.ConnectionError:
            return Response(
                {'error': 'Could not reach ollama.com.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except http_requests.RequestException as exc:
            logger.error(
                '[Hypothalamus] fetch_catalog failed: %s', exc
            )
            return Response(
                {'error': f'Could not reach ollama.com: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        entries = scrape_ollama_library(resp.text)

        created_count = 0
        updated_count = 0
        errors = []

        for entry in entries:
            try:
                was_created = _process_catalog_entry(entry)
                if was_created:
                    created_count += 1
                else:
                    updated_count += 1
            except Exception as exc:
                logger.warning(
                    '[Hypothalamus] Failed to process catalog entry %s: %s',
                    entry.get('name', 'unknown'),
                    exc,
                )
                errors.append(f'{entry.get("name", "unknown")}: {exc}')

        async_to_sync(fire_neurotransmitter)(
            Acetylcholine(
                receptor_class='AIModel',
                dendrite_id='fetch_catalog',
                activity='updated',
                vesicle={'action': 'fetch_catalog'},
            )
        )

        total_fetched = created_count + updated_count
        logger.info(
            '[Hypothalamus] fetch_catalog complete. '
            'Fetched: %d, Created: %d, Updated: %d',
            total_fetched,
            created_count,
            updated_count,
        )

        return Response({
            'fetched': total_fetched,
            'created': created_count,
            'updated': updated_count,
            'errors': errors,
        })


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
