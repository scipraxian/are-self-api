from django.contrib import admin
from .models import (
    HydraSpellbook,
    HydraSpell,
    HydraSpawn,
    HydraHead,
    HydraHeadStatus,
    HydraSpawnStatus
)


@admin.register(HydraSpellbook)
class HydraSpellbookAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'created')


@admin.register(HydraSpell)
class HydraSpellAdmin(admin.ModelAdmin):
    # Show both Old and New executables in the list for easy auditing
    list_display = ('name', 'order', 'talos_executable', 'deprecated_executable_display')
    list_editable = ('order',)
    list_filter = ('talos_executable',)

    # Use filter_horizontal for the new switches M2M
    filter_horizontal = ('switches',)

    # Organize fields to make the migration obvious
    fieldsets = (
        ('Identity', {
            'fields': ('name', 'description', 'spellbook', 'order')
        }),
        ('New Configuration (Talos)', {
            'fields': ('talos_executable', 'switches'),
            'description': "Select the new Talos Executable and any specific override switches."
        }),
        ('Deprecated Configuration', {
            'fields': ('executable', 'active_switches'),
            'classes': ('collapse',),
            'description': "Old configuration. Reference this to set the new one, then ignore."
        }),
    )

    def deprecated_executable_display(self, obj):
        """Helper to show the old executable name safely."""
        return obj.executable.name if obj.executable else "-"

    deprecated_executable_display.short_description = "Old Executable"


@admin.register(HydraSpawn)
class HydraSpawnAdmin(admin.ModelAdmin):
    list_display = ('id', 'spellbook', 'environment', 'status', 'created')
    list_filter = ('status', 'spellbook')


@admin.register(HydraHead)
class HydraHeadAdmin(admin.ModelAdmin):
    list_display = ('id', 'spell_name', 'status', 'created')
    list_filter = ('status', 'spell__name')
    readonly_fields = ('celery_task_id', 'spell_log', 'execution_log')

    def spell_name(self, obj):
        return obj.spell.name


# Simple registrations for Statuses
admin.site.register(HydraHeadStatus)
admin.site.register(HydraSpawnStatus)