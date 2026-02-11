from django.contrib import admin

# [NEW] Import ProjectEnvironment to resolve context for previews
from environments.models import ProjectEnvironment
from hydra.utils import (
    get_active_environment,
    resolve_environment_context,
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
    HydraTag,
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
    fk_name = 'spellbook'


class HydraSpellbookWireInline(admin.TabularInline):
    """Shows the wires."""

    model = HydraSpellbookConnectionWire
    extra = 0
    fk_name = 'spellbook'
    verbose_name = 'Wire'


@admin.register(HydraTag)
class HydraTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(HydraSpellbook)
class HydraSpellbookAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'is_favorite', 'created', 'node_count')
    list_filter = ('is_favorite', 'tags')
    filter_horizontal = ('tags',)
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
            # [FIX] Fetch the currently selected environment for context
            env = ProjectEnvironment.objects.filter(selected=True).first()

            # Pass the environment to the renderer
            full_cmd_list = obj.get_full_command(environment=env)

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

            env = get_active_environment(obj)
            ctx = resolve_environment_context(head_id=obj.id)

            full_cmd_list = obj.spell.get_full_command(
                environment=env, extra_context=ctx
            )
            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error: {str(e)}'


@admin.register(HydraSpellbookNode)
class HydraSpellbookNodeAdmin(admin.ModelAdmin):
    """
    Instance-level configuration for Spells on a Graph.
    """

    list_display = ('id', 'spellbook', 'spell', 'distribution_mode', 'is_root')
    list_filter = ('spellbook', 'spell', 'distribution_mode')
    raw_id_fields = ('spellbook', 'spell', 'invoked_spellbook')

    fieldsets = (
        ('Graph Placement', {'fields': ('spellbook', 'ui_json', 'is_root')}),
        (
            'Execution Logic',
            {
                'fields': ('spell', 'invoked_spellbook', 'distribution_mode'),
                'description': "If Distribution Mode is empty, Talos will use the Spell's default strategy.",
            },
        ),
    )


admin.site.register(HydraHeadStatus)
admin.site.register(HydraSpawnStatus)
admin.site.register(HydraSpawn)
