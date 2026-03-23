import datetime
import os
from uuid import UUID

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
    """
    Provider-level network configuration for LLM backends (LiteLLM).
    """

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
        help_text='Environment variable name that stores the API key (e.g. OPENROUTER_API_KEY).',
    )

    class Meta:
        verbose_name_plural = 'Model Providers'

    def natural_key(self):
        return self.name

    @property
    def has_active_key(self) -> bool:
        """
        Dynamically checks if the server actually possesses the funds/keys
        required to use this provider at this exact moment.
        """
        if not self.requires_api_key:
            return True
        if not self.api_key_env_var:
            return False

        # Check Django settings first, then fall back to OS environment
        key = getattr(settings, self.api_key_env_var, None) or os.environ.get(
            self.api_key_env_var
        )
        return bool(key and key.strip())


class AIModelCategory(NameMixin, DescriptionMixin):
    """Category for AI models, e.g., 'Text Generation', 'Vision', 'Coding'."""

    pass


class AIMode(NameMixin, DescriptionMixin):
    """Mode for AI models, e.g., 'chat', 'embedding', 'completion'."""

    pass


class AIModelFamily(NameMixin, DescriptionMixin):
    """
    Groups models into conceptual lineages (e.g., 'Claude 3.5', 'Llama 3').
    Allows the Swarm to understand that different physical endpoints are the same 'Brain'.

    NOTE Name must be unique AND slug must be unique.
    slug is what we use to help identify the family.
    """

    slug = models.SlugField(unique=True, default='llama-3-70b-instruct')

    class Meta:
        verbose_name_plural = 'AI Model Families'


class AIModel(UUIDIdMixin, NameMixin, DescriptionMixin):
    """
    The Semantic Model Catalog. Represents the mathematical 'Brain' conceptually
    (e.g., "Llama 3 70B"), regardless of who is hosting it.
    """

    RELATED_NAME = 'ai_models'

    family = models.ForeignKey(
        AIModelFamily,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=RELATED_NAME,
    )

    # Hard Constraints (The Filters)
    context_length = models.IntegerField(db_index=True)

    enabled = models.BooleanField(default=True, db_index=True)

    # Connect to the LiteLLM Categories
    categories = models.ManyToManyField(AIModelCategory, blank=True)
    supports_vision = models.BooleanField(default=False, db_index=True)
    supports_function_calling = models.BooleanField(
        default=False, db_index=True
    )
    supports_parallel_function_calling = models.BooleanField(default=False)
    supports_response_schema = models.BooleanField(default=False)
    supports_system_messages = models.BooleanField(default=True)
    supports_prompt_caching = models.BooleanField(default=False)
    supports_reasoning = models.BooleanField(default=False)
    supports_audio_input = models.BooleanField(default=False)
    supports_audio_output = models.BooleanField(default=False)
    supports_web_search = models.BooleanField(default=False)

    deprecation_date = models.DateField(null=True, blank=True)

    # Semantic Constraints (The Math)
    # Using 768 dimensions (standard for nomic-embed-text)
    vector = VectorField(dimensions=768, null=True, blank=True)

    def update_vector(self):
        from frontal_lobe.synapse import OllamaClient

        registry = ModelRegistry.objects.get(id=ModelRegistry.NOMIC_EMBED_TEXT)
        client = OllamaClient(registry.name)

        cat_names = ', '.join(self.categories.values_list('name', flat=True))
        rich_text = (
            f'Model Name: {self.name}. '
            f'Categories: {cat_names}. '
            f'Description: {self.description or "General AI inference model."}'
        )
        self.vector = client.embed(rich_text)
        self.save(update_fields=['vector'])


class AIModelProviderRateLimitMixin(models.Model):
    """Rate limit tracking for AI model providers."""

    rate_limited_on = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the 429 Too Many Requests was hit.',
    )
    rate_limit_reset_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text='The exact time this model is allowed back into the routing pool.',
    )
    rate_limit_reset_interval = models.DurationField(
        null=True,
        blank=True,
        default=datetime.timedelta(seconds=60),
        help_text='Base cooldown duration.',
    )
    rate_limit_counter = models.IntegerField(
        default=0,
        help_text='Tracks consecutive failures for Exponential Backoff.',
    )
    rate_limit_total_failures = models.IntegerField(
        default=0, help_text='Tracks total failures for this model.'
    )

    class Meta:
        abstract = True

    def trip_circuit_breaker(self):
        """
        Calculates exponential backoff and evicts the model from the routing pool.
        Fail 1: 1 min, Fail 2: 2 mins, Fail 3: 4 mins...
        """
        self.rate_limited_on = timezone.now()
        self.rate_limit_counter += 1
        self.rate_limit_total_failures += 1

        # Exponential backoff math: interval * (2 ^ (failures - 1))
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
        """Called upon a successful request to clear the breaker state."""
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
    """The physical routing string and token limits."""

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


class AIModelPricingAbstract(CreatedMixin, ModifiedMixin):
    """
    1:1 map of the LiteLLM Cost spec.
    Massive decimal precision to handle scientific notation (3e-05).
    """

    is_current = models.BooleanField(default=False, db_index=True)
    model_provider = models.ForeignKey(
        AIModelProvider, on_delete=models.CASCADE
    )
    is_active = models.BooleanField(default=True, db_index=True)

    # STANDARD COSTS
    input_cost_per_token = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True, db_index=True
    )
    output_cost_per_token = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )

    # CHARACTER COSTS (For older models or specific providers like Vertex)
    input_cost_per_character = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )
    output_cost_per_character = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )

    # OVERAGE COSTS (The > 128k context penalty tier)
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
    )  # for o1/o3 models
    cache_read_input_token_cost = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )  # Claude/Gemini prompt caching
    cache_creation_input_token_cost = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )  # Claude/Gemini prompt caching
    input_cost_per_audio_token = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )  # Whisper / Gemini audio

    # EMBEDDING SPECIFIC
    output_vector_size = models.IntegerField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ['-is_current', 'model_provider__provider__key']


class AIModelPricing(AIModelPricingAbstract):
    pass


class AIModelProviderUsageRecord(AIModelPricingAbstract):
    RELATED_NAME = 'usage_records'

    # References.

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

    # PRE-SEND
    request_payload = models.JSONField(blank=True, default=dict)
    tool_payload = models.JSONField(blank=True, default=dict)
    estimated_cost = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )

    # POST-SEND
    query_time = models.DurationField(null=True, blank=True)
    response_payload = models.JSONField(blank=True, default=dict)

    # Provider INPUT Token Usage
    input_tokens = models.IntegerField(default=0)
    cache_read_input_tokens = models.IntegerField(default=0)
    cache_creation_input_tokens = models.IntegerField(default=0)

    # Provider OUTPUT Token Usage
    output_tokens = models.IntegerField(default=0)
    reasoning_tokens = models.IntegerField(default=0)
    audio_tokens = models.IntegerField(default=0)

    actual_cost = models.DecimalField(
        max_digits=25, decimal_places=15, null=True, blank=True
    )


class SyncStatus(NameMixin):
    RUNNING = 1  # 'RUNNING', 'Running'
    SUCCESS = 2  # 'SUCCESS', 'Success'
    FAILED = 3  # 'FAILED', 'Failed'


class AIModelSyncLog(CreatedAndModifiedWithDelta):
    """Audit trail and mutex lock for the Hypothalamus sync job."""

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
