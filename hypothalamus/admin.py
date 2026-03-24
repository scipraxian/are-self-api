from django.contrib import admin

from .models import (
    AIMode,
    AIModel,
    AIModelCapabilities,
    AIModelCategory,
    AIModelDescription,
    AIModelFamily,
    AIModelPricing,
    AIModelProvider,
    AIModelProviderUsageRecord,
    AIModelSyncLog,
    AIModelTags,
    LLMProvider,
    SyncStatus,
)

# ------------------------------------------------------------------ #
#  Network & Classification                                          #
# ------------------------------------------------------------------ #


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'key',
        'requires_api_key',
        'has_active_key',
    )
    search_fields = ('name', 'key', 'base_url')
    list_filter = ('requires_api_key',)
    readonly_fields = ('has_active_key',)


@admin.register(AIModelCapabilities)
class AIModelCapabilitiesAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(AIModelTags)
class AIModelTagsAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(AIModelCategory)
class AIModelCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(AIModelFamily)
class AIModelFamilyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')


@admin.register(AIMode)
class AIModeAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(SyncStatus)
class SyncStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ('id',)


# ------------------------------------------------------------------ #
#  The Semantic Brain & Routing                                      #
# ------------------------------------------------------------------ #


class AIModelDescriptionInline(admin.StackedInline):
    model = AIModelDescription.ai_models.through
    extra = 0
    verbose_name = 'Semantic Profile'
    verbose_name_plural = 'Semantic Profiles'


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'context_length',
        'enabled',
        'get_capabilities',
        'vector_status',
    )
    search_fields = ('name', 'description')
    list_filter = ('enabled', 'capabilities')
    inlines = [AIModelDescriptionInline]

    readonly_fields = ('vector_display',)

    def get_capabilities(self, obj):
        return ', '.join([c.name for c in obj.capabilities.all()])

    get_capabilities.short_description = 'Capabilities'

    def vector_status(self, obj):
        return '✅ Embedded' if obj.vector else '❌ Missing'

    vector_status.short_description = 'Vector Status'

    def vector_display(self, obj):
        if obj.vector is None:
            return 'None'
        try:
            return f'Vector({len(obj.vector)} dimensions)'
        except (TypeError, ValueError):
            return 'Invalid Vector'

    vector_display.short_description = 'Vector'

    fieldsets = (
        (
            'Core Attributes',
            {
                'fields': (
                    'name',
                    'description',
                    'context_length',
                    'enabled',
                    'deprecation_date',
                )
            },
        ),
        ('Capabilities', {'fields': ('capabilities',)}),
        (
            'Vector Math',
            {'fields': ('vector_display',), 'classes': ('collapse',)},
        ),
    )


@admin.register(AIModelDescription)
class AIModelDescriptionAdmin(admin.ModelAdmin):
    list_display = ('get_models', 'is_current', 'created')
    list_filter = ('is_current', 'tags', 'categories')
    search_fields = ('description', 'ai_models__name')
    filter_horizontal = ('ai_models', 'families', 'categories', 'tags')

    def get_models(self, obj):
        return ', '.join([m.name for m in obj.ai_models.all()[:3]]) + (
            '...' if obj.ai_models.count() > 3 else ''
        )

    get_models.short_description = 'Attached Models'


class AIModelPricingInline(admin.TabularInline):
    """
    CRITICAL FOR DEBUGGING: The router filters out providers without active/current pricing.
    This lets you see immediately if pricing is attached.
    """

    model = AIModelPricing
    extra = 0
    fields = (
        'is_current',
        'is_active',
        'input_cost_per_token',
        'output_cost_per_token',
    )
    readonly_fields = ('input_cost_per_token', 'output_cost_per_token')


@admin.register(AIModelProvider)
class AIModelProviderAdmin(admin.ModelAdmin):
    list_display = (
        'provider_unique_model_id',
        'ai_model',
        'provider',
        'mode',
        'is_rate_limited',
    )
    search_fields = (
        'provider_unique_model_id',
        'ai_model__name',
        'provider__key',
    )
    list_filter = ('provider', 'mode')
    raw_id_fields = (
        'ai_model',
        'provider',
    )
    inlines = [AIModelPricingInline]

    fieldsets = (
        (
            'Routing Specs',
            {
                'fields': (
                    'ai_model',
                    'provider',
                    'provider_unique_model_id',
                    'mode',
                )
            },
        ),
        (
            'Token Limits',
            {'fields': ('max_tokens', 'max_input_tokens', 'max_output_tokens')},
        ),
        (
            'Circuit Breaker',
            {
                'fields': (
                    'rate_limited_on',
                    'rate_limit_reset_time',
                    'rate_limit_counter',
                    'rate_limit_total_failures',
                )
            },
        ),
    )

    def is_rate_limited(self, obj):
        from django.utils import timezone

        if (
            obj.rate_limit_reset_time
            and obj.rate_limit_reset_time > timezone.now()
        ):
            return '⚠️ YES'
        return '✅ Clear'

    is_rate_limited.short_description = 'Circuit Breaker'


# ------------------------------------------------------------------ #
#  The FinOps Ledgers                                                #
# ------------------------------------------------------------------ #


@admin.register(AIModelPricing)
class AIModelPricingAdmin(admin.ModelAdmin):
    list_display = (
        'model_provider',
        'is_current',
        'is_active',
        'input_cost_per_token',
        'output_cost_per_token',
    )
    list_filter = ('is_current', 'is_active', 'model_provider__provider')
    search_fields = ('model_provider__provider_unique_model_id',)
    raw_id_fields = ('model_provider',)


@admin.register(AIModelProviderUsageRecord)
class AIModelProviderUsageRecordAdmin(admin.ModelAdmin):
    list_display = (
        'created',
        'identity_disc',
        'ai_model_provider',
        'input_tokens',
        'output_tokens',
        'estimated_cost',
    )
    list_filter = ('ai_model_provider__provider', 'created')
    search_fields = (
        'identity_disc__name',
        'ai_model_provider__provider_unique_model_id',
    )
    raw_id_fields = ('ai_model_provider', 'ai_model', 'identity_disc')
    date_hierarchy = 'created'


@admin.register(AIModelSyncLog)
class AIModelSyncLogAdmin(admin.ModelAdmin):
    list_display = (
        'created',
        'status',
        'models_added',
        'prices_updated',
        'models_deactivated',
    )
    list_filter = ('status', 'created')
    readonly_fields = ('created', 'modified')
    date_hierarchy = 'created'
