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
class LLMProvider(UUIDIdMixin, DefaultFieldsMixin, DescriptionMixin):
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


class AIModelCategory(UUIDIdMixin, NameMixin, DescriptionMixin):
    """I saw this word."""

    pass


class AIModelCapabilities(UUIDIdMixin, NameMixin, DescriptionMixin):
    """Dynamically tracks things like 'vision', 'function_calling', 'reasoning'."""

    pass


class AIModelTags(UUIDIdMixin, NameMixin, DescriptionMixin):
    """Everything Else we come across, tag it."""

    pass


class AIMode(UUIDIdMixin, NameMixin, DescriptionMixin):
    """Mode for AI models, e.g., 'chat', 'embedding', 'completion'."""

    pass


class AIModelFamily(UUIDIdMixin, NameMixin, DescriptionMixin):
    """Groups models into conceptual lineages (e.g., 'Claude 3.5', 'Llama 3')."""

    slug = models.SlugField(unique=True, default='llama-3-70b-instruct')
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subfamilies',
        help_text='Parent family. E.g., "Qwen Coder" parent is "Qwen".',
    )

    class Meta:
        verbose_name_plural = 'AI Model Families'


class AIModelVersion(UUIDIdMixin, NameMixin, DescriptionMixin):
    """Version of an AI model, e.g., '1.0', '2.0', '3.0'."""

    pass


class AIModelCreator(UUIDIdMixin, NameMixin, DescriptionMixin):
    """The organization or group that trained the model (e.g., Meta, Alibaba, Mistral)."""

    class Meta:
        verbose_name_plural = 'AI Model Creators'


class AIModelRole(UUIDIdMixin, NameMixin, DescriptionMixin):
    """The intended use-case or fine-tuning style (e.g., instruct, base, coder, uncensored)."""

    pass


class AIModelQuantization(UUIDIdMixin, NameMixin, DescriptionMixin):
    """The compression format, crucial for local hardware routing (e.g., q4_0, awq, fp16)."""

    pass


class AIModel(UUIDIdMixin, NameMixin, DescriptionMixin):
    """The Semantic Model Catalog. Represents the mathematical 'Brain' conceptually."""

    RELATED_NAME = 'ai_models'
    creator = models.ForeignKey(
        AIModelCreator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=RELATED_NAME,
    )
    roles = models.ManyToManyField(
        AIModelRole,
        blank=True,
        related_name=RELATED_NAME,
    )
    quantizations = models.ManyToManyField(
        AIModelQuantization,
        blank=True,
        related_name=RELATED_NAME,
    )
    parameter_size = models.FloatField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Parameter count in billions (e.g., 70.0 for 70B, 0.5 for 500M).',
    )
    family = models.ForeignKey(
        AIModelFamily,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=RELATED_NAME,
    )
    version = models.ForeignKey(
        AIModelVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=RELATED_NAME,
    )

    context_length = models.IntegerField(db_index=True)
    enabled = models.BooleanField(default=True, db_index=True)
    capabilities = models.ManyToManyField(AIModelCapabilities, blank=True)
    deprecation_date = models.DateField(null=True, blank=True)

    @property
    def vector(self):
        """Silently fetches the vector from the 1:1 table."""
        if hasattr(self, 'vector_node'):
            return self.vector_node.embeddings
        return None

    @vector.setter
    def vector(self, value):
        """Silently updates or creates the 1:1 record."""
        if not hasattr(self, 'vector_node'):
            AIModelVector.objects.create(ai_model=self, embeddings=value)
        else:
            self.vector_node.embeddings = value
            self.vector_node.save(update_fields=['embeddings'])

    def update_vector(self):
        from frontal_lobe.synapse import OllamaClient

        client = OllamaClient('nomic-embed-text')
        cap_names = ', '.join(self.capabilities.values_list('name', flat=True))

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

        role_names = (
            ', '.join(self.roles.values_list('name', flat=True)) or 'General'
        )
        quant_names = (
            ', '.join(self.quantizations.values_list('name', flat=True))
            or 'Unquantized/Unknown'
        )

        creator_name = self.creator.name if self.creator else 'Unknown Creator'
        family_name = self.family.name if self.family else 'Unknown Family'
        size_str = (
            f'{self.parameter_size}B' if self.parameter_size else 'Unknown Size'
        )

        # The new, hyper-enriched vector payload!
        rich_text = (
            f'Model Name: {self.name}. '
            f'Creator: {creator_name}. '
            f'Family: {family_name}. '
            f'Size: {size_str}. '
            f'Roles: {role_names}. '
            f'Quantizations: {quant_names}. '
            f'Categories: {cat_names}. '
            f'Tags: {tag_names}. '
            f'Capabilities: {cap_names}. '
            f'Description: {desc_text}'
        )
        self.vector = client.embed(rich_text)
        self.save(update_fields=['vector'])


class AIModelVector(UUIDIdMixin, models.Model):
    """Offloads the heavy 768-dimensional vector to keep AIModel queries and fixtures clean."""

    ai_model = models.OneToOneField(
        'hypothalamus.AIModel',
        on_delete=models.CASCADE,
        related_name='vector_node',
    )
    embeddings = VectorField(dimensions=768, null=True, blank=True)


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

    MAX_CIRCUIT_BREAKER_COOLDOWN = datetime.timedelta(minutes=5)
    RESOURCE_COOLDOWN = datetime.timedelta(seconds=60)

    def trip_resource_cooldown(self):
        """Short, flat cooldown for host-resource errors (OOM, etc.).

        Unlike trip_circuit_breaker this does NOT escalate, does NOT
        increment rate_limit_counter, and always applies the same fixed
        pause.  The provider is not at fault — the host just needs a
        moment to free resources.
        """
        self.rate_limited_on = timezone.now()
        self.rate_limit_reset_time = (
            self.rate_limited_on + self.RESOURCE_COOLDOWN
        )
        self.save(
            update_fields=['rate_limited_on', 'rate_limit_reset_time']
        )

    def trip_circuit_breaker(self):
        self.rate_limited_on = timezone.now()
        self.rate_limit_counter += 1
        self.rate_limit_total_failures += 1

        # Cap the exponent to prevent overflow when computing cooldown
        capped_exponent = min(self.rate_limit_counter - 1, 10)
        multiplier = 2 ** capped_exponent
        cooldown = min(
            self.rate_limit_reset_interval * multiplier,
            self.MAX_CIRCUIT_BREAKER_COOLDOWN,
        )

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
    UUIDIdMixin, CreatedMixin, ModifiedMixin, AIModelProviderRateLimitMixin
):
    is_enabled = models.BooleanField(default=True, db_index=True)

    # References
    ai_model = models.ForeignKey(AIModel, on_delete=models.CASCADE)
    provider = models.ForeignKey(LLMProvider, on_delete=models.CASCADE)

    # PROVIDER + MODEL
    provider_unique_model_id = models.CharField(
        max_length=255, unique=True, db_index=True
    )
    # MODE 'image_generation', 'chat', 'embedding'
    # CANONICAL MODE CHOICE FOR THIS MODEL PROVIDER NO MODE NO WORK.
    mode = models.ForeignKey(
        AIMode, on_delete=models.SET_NULL, null=True, blank=True
    )

    # Occasional provider specific token limiters.
    max_tokens = models.IntegerField(null=True, blank=True)
    max_input_tokens = models.IntegerField(null=True, blank=True)
    max_output_tokens = models.IntegerField(null=True, blank=True)

    disabled_capabilities = models.ManyToManyField(
        AIModelCapabilities, blank=True
    )

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


class AIModelPricing(UUIDIdMixin, AIModelPricingAbstract):
    pass


class AIModelProviderUsageRecord(UUIDIdMixin, AIModelFinOpsAbstract):
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


class FailoverStrategy(UUIDIdMixin, NameMixin, DescriptionMixin):
    """
    A reusable, ordered sequence of failover steps.
    The strategy is defined entirely by its assignments — no scalar flags needed.
    e.g. 'Standard Cloud' = [family_failover(1), vector_search(2)]
         'Local First'    = [local_fallback(1), family_failover(2), strict_fail(3)]
    """

    class Meta:
        verbose_name = 'Failover Strategy'
        verbose_name_plural = 'Failover Strategies'


class FailoverType(UUIDIdMixin, NameMixin, DescriptionMixin):
    """
    A discrete failover step, e.g.:
    'family_failover', 'vector_search', 'local_fallback', 'strict_fail'
    'force_filters', etc?
    """

    class Meta:
        verbose_name = 'Failover Type'
        verbose_name_plural = 'Failover Types'


class FailoverStrategyStep(UUIDIdMixin, models.Model):
    """
    One step in a FailoverStrategy's execution chain.
    """

    strategy = models.ForeignKey(
        FailoverStrategy,
        on_delete=models.CASCADE,
        related_name='steps',
    )
    failover_type = models.ForeignKey(
        FailoverType,
        on_delete=models.PROTECT,  # Don't silently orphan steps
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Failover Strategy Step'
        verbose_name_plural = 'Failover Strategy Steps'
        ordering = ['order']
        unique_together = [
            ('strategy', 'order')
        ]  # Prevent duplicate priority slots


class AIModelSelectionFilter(UUIDIdMixin, NameMixin):
    """
    Defines the routing policy for a Persona or Task.
    Acts as a pre-filter before Hypothalamus vector selection.
    """

    # Drives the full degradation chain when preferred_model is unavailable
    failover_strategy = models.ForeignKey(
        FailoverStrategy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # Sets the MODE, Provider, and Model baseline in one FK
    preferred_model = models.ForeignKey(
        AIModelProvider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='selection_filter_preferred',
        help_text='Bypass vector search and use this specific provider+model first.',
    )
    local_failover = models.ForeignKey(
        AIModelProvider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='selection_filter_local',
        help_text='Explicit local model to try when the failover strategy permits it.',
    )

    required_capabilities = models.ManyToManyField(
        AIModelCapabilities,
        blank=True,
        help_text='Hard requirement — candidate models MUST have all of these.',
    )
    banned_providers = models.ManyToManyField(
        LLMProvider,
        blank=True,
        help_text='Never route to these providers, even as a fallback.',
    )

    # --- Semantic Weights (Vector Boosters) ---
    # Soft signals that bias the Hypothalamus query, not hard filters.
    preferred_categories = models.ManyToManyField(AIModelCategory, blank=True)
    preferred_tags = models.ManyToManyField(AIModelTags, blank=True)
    preferred_roles = models.ManyToManyField(AIModelRole, blank=True)


class SyncStatus(UUIDIdMixin, NameMixin):
    RUNNING = UUID('d5f70087-3690-4c3d-b03a-35d04a9846c0')
    SUCCESS = UUID('87a8b8f9-63e1-4f7b-933a-a7e51bb786e6')
    FAILED = UUID('8c55e942-09ac-4e96-b086-a54838d099ef')


class AIModelSyncLog(UUIDIdMixin, CreatedAndModifiedWithDelta):
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


class AIModelRating(UUIDIdMixin, CreatedMixin):
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


class LiteLLMCache(UUIDIdMixin, CreatedMixin):
    cached_catalog = models.JSONField(default=dict)


class AIModelDescriptionCache(UUIDIdMixin, CreatedMixin):
    cached_library = models.JSONField(default=dict)


class AIModelDescription(UUIDIdMixin, DescriptionMixin, CreatedAndModifiedWithDelta):
    """Parsed from Description Cache."""

    ai_models = models.ManyToManyField(AIModel, blank=True)
    families = models.ManyToManyField(AIModelFamily, blank=True)
    categories = models.ManyToManyField(AIModelCategory, blank=True)
    tags = models.ManyToManyField(AIModelTags, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)


class AIModelSyncReport(UUIDIdMixin, CreatedMixin):
    """Captures proposed taxonomy that the sync would have created but didn't.

    Attached 1:1 to an AIModelSyncLog. Human reviews this, updates
    canonical fixtures, then the next sync picks up the new records.
    """

    sync_log = models.OneToOneField(
        AIModelSyncLog,
        on_delete=models.CASCADE,
        related_name='sync_report',
    )

    # Each field is a JSON list of {"raw_slug": "...", "proposed_name": "..."}
    proposed_families = models.JSONField(default=list)
    proposed_creators = models.JSONField(default=list)
    proposed_roles = models.JSONField(default=list)
    proposed_quantizations = models.JSONField(default=list)
    proposed_tags = models.JSONField(default=list)
    proposed_versions = models.JSONField(default=list)

    # Models that couldn't be fully enriched because taxonomy was missing
    unenriched_model_slugs = models.JSONField(default=list)

    def __str__(self):
        total = (
            len(self.proposed_families)
            + len(self.proposed_creators)
            + len(self.proposed_roles)
            + len(self.proposed_tags)
            + len(self.proposed_versions)
        )
        return f'SyncReport ({total} proposed) for {self.sync_log}'
