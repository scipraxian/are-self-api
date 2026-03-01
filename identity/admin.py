from django.contrib import admin

from .models import (
    Identity,
    IdentityAddon,
    IdentityDisc,
    IdentityTag,
    IdentityType,
)


@admin.register(IdentityAddon)
class IdentityAddonAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')


@admin.register(IdentityTag)
class IdentityTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(IdentityType)
class IdentityTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ('name', 'identity_type', 'created', 'modified')
    list_filter = ('identity_type', 'tags', 'created')
    search_fields = ('name', 'system_prompt_template')
    filter_horizontal = ('tags', 'addons', 'enabled_tools')
    readonly_fields = ('id', 'created', 'modified', 'delta')

    fieldsets = (
        (None, {
            'fields': ('name', 'identity_type')
        }),
        ('Configuration', {
            'fields': ('system_prompt_template', 'tags', 'addons', 'enabled_tools')
        }),
        ('Metadata', {
            'classes': ('collapse',),
            'fields': ('id', 'created', 'modified', 'delta'),
        }),
    )


@admin.register(IdentityDisc)
class IdentityDiscAdmin(admin.ModelAdmin):
    list_display = ('name', 'identity', 'level', 'xp', 'available', 'successes', 'failures')
    list_filter = ('available', 'level', 'identity')
    search_fields = ('name', 'identity__name', 'last_message_to_self')
    filter_horizontal = ('memories',)
    readonly_fields = (
        'id',
        'created',
        'modified',
        'delta',
        'xp',
        'level',
        'successes',
        'failures',
        'timeouts',
        'last_turn',
    )

    fieldsets = (
        (None, {
            'fields': ('name', 'identity', 'available')
        }),
        ('Runtime State', {
            'fields': ('last_message_to_self', 'last_turn', 'memories')
        }),
        ('Progression & Stats', {
            'fields': (
                ('level', 'xp'),
                ('successes', 'failures', 'timeouts'),
            )
        }),
        ('Metadata', {
            'classes': ('collapse',),
            'fields': ('id', 'created', 'modified', 'delta'),
        }),
    )
