from django.contrib import admin
from .models import (
    HydraSpellbook,
    HydraSpell,
    HydraSpawn,
    HydraHead,
    HydraHeadStatus,
    HydraSpawnStatus,
    HydraSwitch,
    HydraSpellArgumentAssignment  # New Model
)


@admin.register(HydraSpellbook)
class HydraSpellbookAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'created')


class HydraSpellArgumentInline(admin.TabularInline):
    """
    Allows adding ordered arguments (e.g. Map Names, Target Platforms)
    directly to the Spell.
    """
    model = HydraSpellArgumentAssignment
    extra = 1
    ordering = ('order',)
    # autocomplete_fields = ['argument'] # Uncomment if you register TalosExecutableArgument with search_fields


@admin.register(HydraSpell)
class HydraSpellAdmin(admin.ModelAdmin):
    # 1. List Display: Shows the migration status (New vs Old)
    list_display = ('name', 'order', 'talos_executable', 'deprecated_executable_display')
    list_editable = ('order',)

    # Filter by the NEW executable to see what's left to migrate
    list_filter = ('talos_executable',)

    # 2. Filter Horizontal: Maintains the UI for BOTH the new switches and the old ones
    filter_horizontal = ('switches', 'active_switches')

    # 3. Inlines: Add the new Argument system
    inlines = [HydraSpellArgumentInline]

    # 4. Fieldsets: Distinct separation between the Future and the Past
    fieldsets = (
        ('Identity', {
            'fields': ('name', 'order')
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


# Simple registrations for Statuses and the deprecated Switch model
admin.site.register(HydraHeadStatus)
admin.site.register(HydraSpawnStatus)
admin.site.register(HydraSwitch)