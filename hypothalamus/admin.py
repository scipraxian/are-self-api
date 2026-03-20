from django.contrib import admin

from .models import (
    AIMode,
    AIModel,
    AIModelCategory,
    AIModelPricing,
    AIModelProvider,
    AIModelProviderUsageRecord,
    AIModelSyncLog,
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
        'base_url',
        'requires_api_key',
        'has_active_key',
    )
    search_fields = ('name', 'key', 'base_url')
    list_filter = ('requires_api_key',)
    readonly_fields = ('has_active_key',)
    fieldsets = (
        (
            'Basic Info',
            {'fields': ('name', 'description', 'key', 'base_url', 'chat_path')},
        ),
        (
            'Authentication',
            {
                'fields': (
                    'requires_api_key',
                    'api_key_header',
                    'api_key_env_var',
                    'has_active_key',
                )
            },
        ),
    )


@admin.register(AIModelCategory)
class AIModelCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(AIMode)
class AIModeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(SyncStatus)
class SyncStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ('id',)


# ------------------------------------------------------------------ #
#  The Semantic Brain & Routing                                      #
# ------------------------------------------------------------------ #


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'context_length',
        'enabled',
        'supports_vision',
        'supports_function_calling',
        'supports_reasoning',
    )
    search_fields = ('name', 'description')
    list_filter = (
        'supports_vision',
        'supports_function_calling',
        'supports_reasoning',
        'categories',
    )
    filter_horizontal = ('categories',)
    # Vectors are massive arrays. Do not let the admin try to render/edit them as text.
    readonly_fields = ('vector_display',)

    def vector_display(self, obj):
        """Displays the vector in a format that avoids truthiness ambiguity."""
        if obj.vector is None:
            return 'None'
        try:
            length = len(obj.vector)
            return f'Vector({length} dimensions)'
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
                    'categories',
                    'deprecation_date',
                )
            },
        ),
        (
            'Capabilities',
            {
                'fields': (
                    'supports_vision',
                    'supports_function_calling',
                    'supports_parallel_function_calling',
                    'supports_response_schema',
                    'supports_system_messages',
                    'supports_prompt_caching',
                    'supports_reasoning',
                    'supports_audio_input',
                    'supports_audio_output',
                    'supports_web_search',
                )
            },
        ),
        (
            'Vector Math',
            {
                'fields': ('vector_display',),
                'classes': ('collapse',),
            },
        ),
    )


@admin.register(AIModelProvider)
class AIModelProviderAdmin(admin.ModelAdmin):
    list_display = ('provider_unique_model_id', 'ai_model', 'provider', 'mode')
    search_fields = (
        'provider_unique_model_id',
        'ai_model__name',
        'provider__name',
    )
    list_filter = ('provider', 'mode')
    raw_id_fields = (
        'ai_model',
        'provider',
    )  # Prevents massive dropdowns if you have 10,000 models


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
    readonly_fields = ('created', 'modified')
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
    readonly_fields = ('created', 'modified')
    raw_id_fields = ('ai_model_provider', 'ai_model', 'identity_disc')
    date_hierarchy = (
        'created'  # Adds a nice date drill-down breadcrumb at the top
    )


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
