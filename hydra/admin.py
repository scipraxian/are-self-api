from django.contrib import admin

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
    HydraSpellBookNodeContext,
    HydraSpellContext,
    HydraSpellTarget,
    HydraTag,
)


class HydraSpellContextInline(admin.TabularInline):
    """Configuration: Default variables for this Spell."""

    model = HydraSpellContext
    extra = 1
    verbose_name = 'Default Variable'
    verbose_name_plural = 'Default Variables (Tier 1)'


class HydraSpellBookNodeContextInline(admin.TabularInline):
    """Configuration: Overrides for this specific Node instance."""

    model = HydraSpellBookNodeContext
    extra = 1
    verbose_name = 'Override Variable'
    verbose_name_plural = 'Override Variables (Tier 2)'


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
    inlines = [
        HydraSpellArgumentInline,
        HydraSpellTargetInline,
        HydraSpellContextInline,
    ]
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

            # [FIX] Resolve Tier 1 Defaults (Spell Context)
            # This fetches the variables defined in HydraSpellContextInline
            ctx = resolve_environment_context(spell_id=obj.id)

            # Pass BOTH the environment and the context to the renderer
            full_cmd_list = obj.get_full_command(
                environment=env, extra_context=ctx
            )

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
        'application_log',
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
    inlines = [HydraSpellBookNodeContextInline]

    # [NEW] Add readonly field
    readonly_fields = ('resolved_command_preview',)

    fieldsets = (
        ('Graph Placement', {'fields': ('spellbook', 'ui_json', 'is_root')}),
        (
            'Execution Logic',
            {
                'fields': ('spell', 'invoked_spellbook', 'distribution_mode'),
                'description': "If Distribution Mode is empty, Talos will use the Spell's default strategy.",
            },
        ),
        # [NEW] Preview Section
        (
            'Context Preview',
            {
                'fields': ('resolved_command_preview',),
                'description': 'Shows the command as it would execute in the currently Selected Environment, applying Spell Defaults and Node Overrides.',
            },
        ),
    )

    def resolved_command_preview(self, obj):
        try:
            if not obj.spell:
                return 'No Spell Assigned'

            # 1. Base Env
            env = ProjectEnvironment.objects.filter(selected=True).first()

            # 2. Spell Defaults (Tier 1)
            # We use the utility to get Env + Spell vars first
            ctx = resolve_environment_context(spell_id=obj.spell.id)

            # 3. Node Overrides (Tier 2)
            # Manually apply these since resolve_environment_context doesn't take node_id directly yet
            node_vars = HydraSpellBookNodeContext.objects.filter(node=obj)
            for var in node_vars:
                if var.key:
                    ctx[var.key] = var.value

            # 4. Render
            full_cmd_list = obj.spell.get_full_command(
                environment=env, extra_context=ctx
            )
            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error generating preview: {str(e)}'


admin.site.register(HydraHeadStatus)
admin.site.register(HydraSpawnStatus)
admin.site.register(HydraSpawn)
