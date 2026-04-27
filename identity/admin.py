from django.contrib import admin
from django.utils.html import format_html

from .identity_prompt import build_identity_prompt, render_base_identity
from .models import (
    BudgetPeriod,
    Identity,
    IdentityAddon,
    IdentityAddonPhase,
    IdentityBudget,
    IdentityBudgetAssignment,
    IdentityDisc,
    IdentityTag,
    IdentityType,
)


# --- SHARED UI HELPER ---
def _render_terminal_preview(prompt_text: str):
    """Renders text inside a simulated terminal block for easy reading."""
    return format_html(
        '<div style="background: #0f172a; color: #e2e8f0; padding: 15px; '
        'border-radius: 6px; border: 1px solid #334155; white-space: pre-wrap; '
        "font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; line-height: 1.5;\">{}</div>",
        prompt_text,
    )


@admin.register(BudgetPeriod)
class BudgetPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration', 'description')
    search_fields = ('name',)


@admin.register(IdentityBudget)
class IdentityBudgetAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'period',
        'max_spend_per_period',
        'max_spend_per_request',
        'max_input_cost_per_token',
    )
    list_filter = ('period',)
    search_fields = ('name',)
    fieldsets = (
        (None, {'fields': ('name', 'description', 'period')}),
        (
            'Model Selection Gates (Per Token)',
            {
                'fields': (
                    'max_input_cost_per_token',
                    'max_output_cost_per_token',
                ),
                'description': 'These dictate which models this budget is even allowed to look at.',
            },
        ),
        (
            'Execution Gates (Total Spend)',
            {
                'fields': (
                    'max_spend_per_period',
                    'max_spend_per_request',
                    'warn_at_percent',
                ),
                'description': 'These halt execution if the persona spends too much.',
            },
        ),
    )


@admin.register(IdentityBudgetAssignment)
class IdentityBudgetAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        'identity_disc',
        'selection_filter',
        'is_active',
        'period_spend_start',
    )
    list_filter = ('is_active',)
    search_fields = ('identity_disc__name', 'selection_filter__name')
    raw_id_fields = (
        'identity_disc',
        'selection_filter',
    )


@admin.register(IdentityType)
class IdentityTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(IdentityTag)
class IdentityTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(IdentityAddon)
class IdentityAddonAdmin(admin.ModelAdmin):
    list_display = ('name', 'phase', 'description', 'genome')
    search_fields = ('name',)
    list_filter = ('genome', 'phase')


class IdentityBudgetAssignmentInline(admin.TabularInline):
    model = IdentityBudgetAssignment
    extra = 0
    fields = ('budget', 'selection_filter', 'is_active', 'period_spend_start')
    raw_id_fields = ('budget', 'selection_filter')


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ('name', 'identity_type', 'created', 'selection_filter', 'genome')
    list_filter = ('genome', 'identity_type')
    search_fields = ('name', 'system_prompt_template')
    filter_horizontal = ('tags', 'addons', 'enabled_tools')
    readonly_fields = ('created', 'modified', 'delta', 'prompt_preview')

    fieldsets = (
        (
            'Persona Core',
            {
                'fields': (
                    'name',
                    'identity_type',
                    'system_prompt_template',
                    'selection_filter',
                )
            },
        ),
        (
            'Capabilities & Flavor',
            {
                'fields': ('tags', 'addons', 'enabled_tools'),
            },
        ),
        (
            'System Prompt Preview',
            {
                'fields': ('prompt_preview',),
                'description': 'The baseline persona instructions.',
            },
        ),
        (
            'Bundle Ownership',
            {
                'fields': ('genome',),
            },
        ),
        (
            'System Info',
            {
                'fields': ('created', 'modified', 'delta'),
                'classes': ('collapse',),
            },
        ),
    )

    def prompt_preview(self, obj):
        if not obj.pk:
            return format_html(
                '<span style="color: #94a3b8; font-style: italic;">'
                'Save the identity to generate a preview.'
                '</span>'
            )
        prompt = render_base_identity(obj)
        return _render_terminal_preview(prompt)

    prompt_preview.short_description = 'Base Output'


@admin.register(IdentityDisc)
class IdentityDiscAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'identity_type',
        'level',
        'xp',
        'available',
        'selection_filter',
        'genome',
    )
    list_filter = (
        'genome',
        'available',
        'level',
        'identity_type',
    )
    search_fields = ('name', 'system_prompt_template')
    readonly_fields = (
        'created',
        'modified',
        'delta',
        'prompt_preview',
        'vector_display',
    )
    filter_horizontal = ('tags', 'addons', 'enabled_tools', 'memories')
    inlines = [IdentityBudgetAssignmentInline]

    fieldsets = (
        (
            'Disc Profile',
            {
                'fields': (
                    'name',
                    'identity_type',
                    'available',
                    'selection_filter',
                )
            },
        ),
        (
            'Persona Core',
            {'fields': ('system_prompt_template',)},
        ),
        (
            'Capabilities & Flavor',
            {
                'fields': ('tags', 'addons', 'enabled_tools'),
            },
        ),
        (
            'Live Statistics',
            {
                'fields': ('level', 'xp', 'successes', 'failures', 'timeouts'),
                'description': 'RPG progression metrics updated by the Frontal Lobe.',
            },
        ),
        (
            'System Prompt Preview',
            {
                'fields': ('prompt_preview',),
                'description': 'The exact system instructions this disc will generate on Turn 1 of its next session.',
            },
        ),
        (
            'Bundle Ownership',
            {
                'fields': ('genome',),
            },
        ),
        (
            'Memory state',
            {
                'fields': (
                    'last_message_to_self',
                    'last_turn',
                    'memories',
                    'vector_display',
                ),
                'classes': ('collapse',),
            },
        ),
        (
            'System Info',
            {
                'fields': ('created', 'modified', 'delta'),
                'classes': ('collapse',),
            },
        ),
    )

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

    def prompt_preview(self, obj):
        if not obj.pk:
            return format_html(
                '<span style="color: #94a3b8; font-style: italic;">'
                'Save the disc to generate a preview.'
                '</span>'
            )
        prompt = build_identity_prompt(obj, turn_number=1)
        return _render_terminal_preview(prompt)

    prompt_preview.short_description = 'Resolved Output'


@admin.register(IdentityAddonPhase)
class IdentityAddonPhaseAdmin(admin.ModelAdmin):
    pass
