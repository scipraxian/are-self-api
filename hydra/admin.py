from django.contrib import admin

# Import the logic we built to resolve the full command list
from hydra.spells.spell_casters.switches_and_arguments import (
    spell_switches_and_arguments,
)

from .models import (
    HydraDistributionMode,  # New
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellArgumentAssignment,
    HydraSpellbook,
    HydraSpellTarget,  # New
    HydraSwitch,
)


@admin.register(HydraDistributionMode)
class HydraDistributionModeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    list_display_links = ('id', 'name')
    ordering = ('id',)
    search_fields = ('name',)


@admin.register(HydraSpellbook)
class HydraSpellbookAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'created', 'display_spells')

    def display_spells(self, obj):
        """Flatten the M2M spells list into a readable string."""
        return ', '.join([spell.name for spell in obj.spells.all()])

    display_spells.short_description = 'Spells'


class HydraSpellArgumentInline(admin.TabularInline):
    """
    Allows adding ordered arguments (e.g. Map Names, Target Platforms)
    directly to the Spell.
    """

    model = HydraSpellArgumentAssignment
    extra = 1
    ordering = ('order',)


class HydraSpellTargetInline(admin.TabularInline):
    """
    Mode 4: Allows pinning specific Agents to this spell.
    """

    model = HydraSpellTarget
    extra = 0
    verbose_name = 'Pinned Target'
    verbose_name_plural = 'Specific Targets (Mode 4 Only)'
    # Raw ID prevents loading a massive dropdown if you have thousands of agents
    raw_id_fields = ['target']


@admin.register(HydraSpell)
class HydraSpellAdmin(admin.ModelAdmin):
    # 1. List Display
    list_display = (
        'name',
        'order',
        'talos_executable',
        'distribution_mode',  # New
        'resolved_command_preview',
    )
    list_editable = ('order',)

    # 2. Filters
    list_filter = ('distribution_mode', 'talos_executable')

    # 3. Filter Horizontal
    filter_horizontal = ('switches', 'active_switches')

    # 4. Inlines: Arguments + Specific Targets
    inlines = [HydraSpellArgumentInline, HydraSpellTargetInline]

    # Added readonly field so it appears in the form view too
    readonly_fields = ('resolved_command_preview',)

    # 5. Fieldsets
    fieldsets = (
        ('Identity', {'fields': ('name', 'order', 'resolved_command_preview')}),
        (
            'Distribution Strategy',
            {
                'fields': ('distribution_mode',),
                'description': (
                    '<strong>Local Server:</strong> Runs on this machine.<br>'
                    '<strong>All Online Agents:</strong> Broadcasts to entire fleet.<br>'
                    '<strong>One Available:</strong> First responder only.<br>'
                    '<strong>Specific Targets:</strong> Use the table below to pin agents.'
                ),
            },
        ),
        (
            'New Configuration (Talos)',
            {
                'fields': ('talos_executable', 'switches'),
                'description': 'Select the new Talos Executable and any specific override switches.',
            },
        ),
        (
            'Deprecated Configuration',
            {
                'fields': ('executable', 'active_switches'),
                'classes': ('collapse',),
                'description': 'Old configuration. Reference this to set the new one, then ignore.',
            },
        ),
    )

    def deprecated_executable_display(self, obj):
        """Helper to show the old executable name safely."""
        return obj.executable.name if obj.executable else '-'

    def resolved_command_preview(self, obj):
        """
        Dynamically builds the command string using the exact same logic
        as the GenericSpellCaster.
        """
        try:
            # 1. Get the list of args/switches
            cmd_list = spell_switches_and_arguments(obj.id)

            # 2. Prepend the executable (GenericSpellCaster logic)
            full_cmd_list = [obj.talos_executable.executable] + cmd_list

            # 3. Join for display
            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error calculating command: {str(e)}'

    deprecated_executable_display.short_description = 'Old Executable'
    resolved_command_preview.short_description = 'Command Preview'


@admin.register(HydraSpawn)
class HydraSpawnAdmin(admin.ModelAdmin):
    list_display = ('id', 'spellbook', 'environment', 'status', 'created')
    list_filter = ('status', 'spellbook')


@admin.register(HydraHead)
class HydraHeadAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'spell_name',
        'status',
        'created',
        'resolved_command_preview',
    )
    list_filter = ('status', 'spell__name')
    readonly_fields = (
        'celery_task_id',
        'spell_log',
        'execution_log',
        'resolved_command_preview',
    )

    def spell_name(self, obj):
        return obj.spell.name

    def resolved_command_preview(self, obj):
        """
        Shows the command string that this Head is configured to run.
        """
        try:
            if not obj.spell:
                return '-'
            cmd_list = spell_switches_and_arguments(obj.spell.id)
            full_cmd_list = [obj.spell.talos_executable.executable] + cmd_list
            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error: {str(e)}'

    resolved_command_preview.short_description = 'Command Executed'


# Simple registrations for Statuses and the deprecated Switch model
admin.site.register(HydraHeadStatus)
admin.site.register(HydraSpawnStatus)
admin.site.register(HydraSwitch)
