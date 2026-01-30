from django.contrib import admin

from hydra.spells.spell_casters.switches_and_arguments import (
    spell_switches_and_arguments,
)

from .models import (
    HydraDistributionMode,
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellArgumentAssignment,
    HydraSpellbook,
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraSpellTarget,
)


@admin.register(HydraDistributionMode)
class HydraDistributionModeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


class HydraSpellbookNodeInline(admin.TabularInline):
    """Shows the nodes contained in this book."""

    model = HydraSpellbookNode
    extra = 0
    verbose_name = 'Graph Node'
    readonly_fields = ('ui_json', 'is_root')


class HydraSpellbookWireInline(admin.TabularInline):
    """Shows the wires."""

    model = HydraSpellbookConnectionWire
    extra = 0
    fk_name = 'spellbook'
    verbose_name = 'Wire'


@admin.register(HydraSpellbook)
class HydraSpellbookAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'created', 'node_count')
    # Use the new Inlines to visualize graph data in Admin
    inlines = [HydraSpellbookNodeInline, HydraSpellbookWireInline]

    def node_count(self, obj):
        return obj.nodes.count()


class HydraSpellArgumentInline(admin.TabularInline):
    model = HydraSpellArgumentAssignment
    extra = 1


class HydraSpellTargetInline(admin.TabularInline):
    model = HydraSpellTarget
    extra = 0
    verbose_name = 'Pinned Target'


@admin.register(HydraSpell)
class HydraSpellAdmin(admin.ModelAdmin):
    # FIXED: Removed 'order' from list_display
    list_display = (
        'name',
        'talos_executable',
        'distribution_mode',
        'resolved_command_preview',
    )
    list_filter = ('distribution_mode', 'talos_executable')
    filter_horizontal = ('switches',)
    inlines = [HydraSpellArgumentInline, HydraSpellTargetInline]
    readonly_fields = ('resolved_command_preview',)

    fieldsets = (
        ('Identity', {'fields': ('name', 'resolved_command_preview')}),
        ('Distribution Strategy', {'fields': ('distribution_mode',)}),
        ('Configuration (Talos)', {'fields': ('talos_executable', 'switches')}),
    )

    def resolved_command_preview(self, obj):
        try:
            cmd_list = spell_switches_and_arguments(obj.id)
            full_cmd_list = [obj.talos_executable.executable] + cmd_list
            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error: {str(e)}'


@admin.register(HydraHead)
class HydraHeadAdmin(admin.ModelAdmin):
    # Added 'node' and 'provenance' to list for debugging
    list_display = (
        'id',
        'spell_name',
        'status',
        'created',
        'node',
        'provenance',
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
        try:
            if not obj.spell:
                return '-'
            cmd_list = spell_switches_and_arguments(obj.spell.id)
            full_cmd_list = [obj.spell.talos_executable.executable] + cmd_list
            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error: {str(e)}'


admin.site.register(HydraHeadStatus)
admin.site.register(HydraSpawnStatus)
admin.site.register(HydraSpawn)
