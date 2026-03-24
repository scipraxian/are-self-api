import datetime
import os

from django.conf import settings
from django.db import models
from django.utils import timezone
from pgvector.django import VectorField

from common.models import (
    CreatedAndModifiedWithDelta,
    CreatedMixin,
    DefaultFieldsMixin,
    DescriptionMixin,
    ModifiedMixin,
    NameMixin,
    UUIDIdMixin,
)
from frontal_lobe.models import ModelRegistry


class LLMProvider(DefaultFieldsMixin, DescriptionMixin):
    """Provider-level network configuration for LLM backends (LiteLLM)."""

    key = models.CharField(
        max_length=50,
        unique=True,
        help_text='Stable identifier, e.g. "ollama", "openrouter", "openai".',
    )
    base_url = models.URLField(
        max_length=255,
        help_text='Base URL for this provider, e.g. https://openrouter.ai/api',
        blank=True,
        null=True,
    )
    chat_path = models.CharField(
        max_length=255,
        default='/v1/chat/completions',
        help_text='Path segment for chat completions, appended to base_url.',
    )
    requires_api_key = models.BooleanField(
        default=True,
        help_text='Whether this provider requires an API key for requests.',
    )
    api_key_header = models.CharField(
        max_length=100,
        default='Authorization',
        help_text='Header name used to send the API key (e.g. Authorization).',
    )
    api_key_env_var = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Environment variable name that stores the API key.',
    )

    class Meta:
        verbose_name_plural = 'Model Providers'

    def natural_key(self):
        return self.name

    @property
    def has_active_key(self) -> bool:
        if not self.requires_api_key:
            return True
        if not self.api_key_env_var:
            return False

        key = getattr(settings, self.api_key_env_var, None) or os.environ.get(
            self.api_key_env_var
        )
        return bool(key and key.strip())


class AIModelCategory(NameMixin, DescriptionMixin):
    """I saw this word."""

    pass


class AIModelCapabilities(NameMixin, DescriptionMixin):
    """Dynamically tracks things like 'vision', 'function_calling', 'reasoning'."""

    pass


class AIModelTags(NameMixin, DescriptionMixin):
    """Everything Else we come across, tag it."""

    pass


class AIMode(NameMixin, DescriptionMixin):
    """Mode for AI models, e.g., 'chat', 'embedding', 'completion'."""

    pass


class AIModelFamily(NameMixin, DescriptionMixin):
    """Groups models into conceptual lineages (e.g., 'Claude 3.5', 'Llama 3')."""

    slug = models.SlugField(unique=True, default='llama-3-70b-instruct')

    class Meta:
        verbose_name_plural = 'AI Model Families'


class AIModel(UUIDIdMixin, NameMixin, DescriptionMixin):
    """The Semantic Model Catalog. Represents the mathematical 'Brain' conceptually."""

    RELATED_NAME = 'ai_models'

    family = models.ForeignKey(
        AIModelFamily,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=RELATED_NAME,
    )

    context_length = models.IntegerField(db_index=True)
    enabled = models.BooleanField(default=True, db_index=True)

    capabilities = models.ManyToManyField(AIModelCapabilities, blank=True)

    deprecation_date = models.DateField(null=True, blank=True)

    # Using 768 dimensions (standard for nomic-embed-text)
    vector = VectorField(dimensions=768, null=True, blank=True)

    def update_vector(self):
        from frontal_lobe.synapse import OllamaClient

        client = OllamaClient('nomic-embed-text')

        cap_names = ', '.join(self.capabilities.values_list('name', flat=True))

        # Traverse backwards to get the currently active description block
        current_desc = self.aimodeldescription_set.filter(
            is_current=True
        ).first()

        if current_desc:
            cat_names = ', '.join(
                current_desc.categories.values_list('name', flat=True)
            )
            tag_names = ', '.join(
                current_desc.tags.values_list('name', flat=True)
            )
            desc_text = (
                current_desc.description or 'General AI inference model.'
            )
        else:
            cat_names = ''
            tag_names = ''
            desc_text = self.description or 'General AI inference model.'

        rich_text = (
            f'Model Name: {self.name}. '
            f'Categories: {cat_names}. '
            f'Tags: {tag_names}. '
            f'Capabilities: {cap_names}. '
            f'Description: {desc_text}'
        )
        self.vector = client.embed(rich_text)
        self.save(update_fields=['vector'])


class AIModelProviderRateLimitMixin(models.Model):
    """Rate limit tracking for AI model providers."""

    rate_limited_on = models.DateTimeField(null=True, blank=True)
    rate_limit_reset_time = models.DateTimeField(null=True, blank=True)
    rate_limit_reset_interval = models.DurationField(
        null=True, blank=True, default=datetime.timedelta(seconds=60)
    )
    rate_limit_counter = models.IntegerField(default=0)
    rate_limit_total_failures = models.IntegerField(default=0)

    class Meta:
        abstract = True

    def trip_circuit_breaker(self):
        self.rate_limited_on = timezone.now()
        self.rate_limit_counter += 1
        self.rate_limit_total_failures += 1

        multiplier = 2 ** (self.rate_limit_counter - 1)
        cooldown = self.rate_limit_reset_interval * multiplier

        self.rate_limit_reset_time = self.rate_limited_on + cooldown
        self.save(
            update_fields=[
                'rate_limited_on',
                'rate_limit_counter',
                'rate_limit_reset_time',
                'rate_limit_total_failures',
            ]
        )

    def reset_circuit_breaker(self):
        if self.rate_limit_counter > 0:
            self.rate_limited_on = None
            self.rate_limit_reset_time = None
            self.rate_limit_counter = 0
            self.save(
                update_fields=[
                    'rate_limited_on',
                    'rate_limit_counter',
                    'rate_limit_reset_time',
                ]
            )


class AIModelProvider(
    CreatedMixin, ModifiedMixin, AIModelProviderRateLimitMixin
):
    ai_model = models.ForeignKey(AIModel, on_delete=models.CASCADE)
    provider = models.ForeignKey(LLMProvider, on_delete=models.CASCADE)
    provider_unique_model_id = models.CharField(
        max_length=255, unique=True, db_index=True
    )
    mode = models.ForeignKey(
        AIMode, on_delete=models.SET_NULL, null=True, blank=True
    )
    max_tokens = models.IntegerField(null=True, blank=True)
    max_input_tokens = models.IntegerField(null=True, blank=True)
    max_output_tokens = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f'{self.ai_model} via {self.provider} ({self.provider_unique_model_id})'


class AIModelFinOpsAbstract(CreatedMixin, ModifiedMixin):
    """Shared financial fields for both Pricing ledgers and Usage receipts."""

    input_cost_per_token = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True, db_index=True
    )
    output_cost_per_token = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )

    input_cost_per_character = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )
    output_cost_per_character = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )

    input_cost_per_token_above_128k_tokens = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )
    output_cost_per_token_above_128k_tokens = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )
    output_cost_per_character_above_128k_tokens = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )

    output_cost_per_reasoning_token = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )
    cache_read_input_token_cost = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )
    cache_creation_input_token_cost = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )
    input_cost_per_audio_token = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )

    output_vector_size = models.IntegerField(null=True, blank=True)

    class Meta:
        abstract = True


class AIModelPricingAbstract(AIModelFinOpsAbstract):
    """The authoritative pricing catalog."""

    is_current = models.BooleanField(default=False, db_index=True)
    model_provider = models.ForeignKey(
        AIModelProvider, on_delete=models.CASCADE
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ['-is_current', 'model_provider__provider__key']


class AIModelPricing(AIModelPricingAbstract):
    pass


class AIModelProviderUsageRecord(AIModelFinOpsAbstract):
    """The individual transaction receipt."""

    RELATED_NAME = 'usage_records'

    ai_model_provider = models.ForeignKey(
        AIModelProvider,
        on_delete=models.CASCADE,
        related_name=RELATED_NAME,
        blank=True,
        null=True,
    )
    ai_model = models.ForeignKey(
        AIModel,
        on_delete=models.CASCADE,
        related_name=RELATED_NAME,
        blank=True,
        null=True,
    )
    identity_disc = models.ForeignKey(
        'identity.IdentityDisc',
        on_delete=models.SET_NULL,
        related_name=RELATED_NAME,
        null=True,
        blank=True,
    )

    request_payload = models.JSONField(blank=True, default=dict)
    tool_payload = models.JSONField(blank=True, default=dict)
    estimated_cost = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )

    query_time = models.DurationField(null=True, blank=True)
    response_payload = models.JSONField(blank=True, default=dict)

    input_tokens = models.IntegerField(default=0)
    cache_read_input_tokens = models.IntegerField(default=0)
    cache_creation_input_tokens = models.IntegerField(default=0)

    output_tokens = models.IntegerField(default=0)
    reasoning_tokens = models.IntegerField(default=0)
    audio_tokens = models.IntegerField(default=0)

    actual_cost = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )


class SyncStatus(NameMixin):
    RUNNING = 1
    SUCCESS = 2
    FAILED = 3


class AIModelSyncLog(CreatedAndModifiedWithDelta):
    status = models.ForeignKey(
        SyncStatus, on_delete=models.SET_NULL, null=True, blank=True
    )
    providers_added = models.IntegerField(default=0)
    models_added = models.IntegerField(default=0)
    prices_updated = models.IntegerField(default=0)
    models_deactivated = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f'Sync {self.created.strftime("%Y-%m-%d %H:%M")} - {self.status}'


class AIModelRating(CreatedMixin):
    ai_model = models.ForeignKey(
        AIModel, on_delete=models.CASCADE, related_name='elo_ratings'
    )
    elo_score = models.FloatField()
    arena_battles = models.IntegerField(default=0)
    confidence_interval = models.FloatField(null=True, blank=True)
    source_leaderboard = models.CharField(max_length=100, default='lmsys')
    is_current = models.BooleanField(default=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['ai_model', 'is_current'])]


class AIModelDescriptionCache(models.Model):
    cached_library = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class AIModelDescription(DescriptionMixin, CreatedAndModifiedWithDelta):
    """Parsed from Description Cache."""

    ai_models = models.ManyToManyField(AIModel, blank=True)
    families = models.ManyToManyField(AIModelFamily, blank=True)
    categories = models.ManyToManyField(AIModelCategory, blank=True)
    tags = models.ManyToManyField(AIModelTags, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)
