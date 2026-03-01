from django.contrib import admin
from django.utils.html import format_html

from .identity_prompt import build_identity_prompt, render_base_identity
from .models import (
    Identity,
    IdentityAddon,
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
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ('name', 'identity_type', 'created')
    list_filter = ('identity_type',)
    search_fields = ('name', 'system_prompt_template')
    filter_horizontal = ('tags', 'addons', 'enabled_tools')
    readonly_fields = ('created', 'modified', 'delta', 'prompt_preview')

    fieldsets = (
        (
            'Persona Core',
            {'fields': ('name', 'identity_type', 'system_prompt_template')},
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
                'description': 'The baseline persona instructions. (Does not include Disc stats).',
            },
        ),
    )

    def prompt_preview(self, obj):
        if not obj.pk:
            return format_html(
                '<span style="color: #94a3b8; font-style: italic;">'
                'Save the identity to generate a preview of its tags and addons.'
                '</span>'
            )
        prompt = render_base_identity(obj)
        return _render_terminal_preview(prompt)

    prompt_preview.short_description = 'Base Output'


@admin.register(IdentityDisc)
class IdentityDiscAdmin(admin.ModelAdmin):
    list_display = ('name', 'identity', 'level', 'xp', 'available')
    list_filter = ('available', 'level', 'identity')
    search_fields = ('name', 'identity__name')
    readonly_fields = ('created', 'modified', 'delta', 'prompt_preview')
    filter_horizontal = ('memories',)

    fieldsets = (
        ('Disc Profile', {'fields': ('name', 'identity', 'available')}),
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
            'Memory state',
            {
                'fields': ('last_message_to_self', 'last_turn', 'memories'),
                'classes': ('collapse',),
            },
        ),
    )

    def prompt_preview(self, obj):
        if not obj.pk or not obj.identity:
            return format_html(
                '<span style="color: #94a3b8; font-style: italic;">'
                'Save the disc and assign an Identity to generate a preview.'
                '</span>'
            )
        prompt = build_identity_prompt(obj, turn_number=1)
        return _render_terminal_preview(prompt)

    prompt_preview.short_description = 'Resolved Output'
