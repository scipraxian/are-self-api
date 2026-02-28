from django.contrib import admin

from environments.models import ProjectEnvironment
from central_nervous_system.utils import (
    get_active_environment,
    resolve_environment_context,
)

from .models import (
    CNSDistributionMode,
    CNSHead,
    CNSHeadStatus,
    CNSSpawn,
    CNSSpawnStatus,
    CNSSpell,
    CNSSpellArgumentAssignment,
    CNSSpellbook,
    CNSSpellbookConnectionWire,
    CNSSpellbookNode,
    CNSSpellBookNodeContext,
    CNSSpellContext,
    CNSSpellTarget,
    CNSTag,
)


class CNSSpellContextInline(admin.TabularInline):
    """Configuration: Default variables for this Spell."""

    model = CNSSpellContext
    extra = 1
    verbose_name = 'Default Variable'
    verbose_name_plural = 'Default Variables (Tier 1)'


class CNSSpellBookNodeContextInline(admin.TabularInline):
    """Configuration: Overrides for this specific Node instance."""

    model = CNSSpellBookNodeContext
    extra = 1
    verbose_name = 'Override Variable'
    verbose_name_plural = 'Override Variables (Tier 2)'


@admin.register(CNSDistributionMode)
class CNSDistributionModeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


class CNSSpellbookNodeInline(admin.TabularInline):
    """Shows the nodes contained in this book."""

    model = CNSSpellbookNode
    extra = 0
    verbose_name = 'Graph Node'
    readonly_fields = ('ui_json', 'is_root')
    fk_name = 'spellbook'


class CNSSpellbookWireInline(admin.TabularInline):
    """Shows the wires."""

    model = CNSSpellbookConnectionWire
    extra = 0
    fk_name = 'spellbook'
    verbose_name = 'Wire'


@admin.register(CNSTag)
class CNSTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(CNSSpellbook)
class CNSSpellbookAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'is_favorite', 'created', 'node_count')
    list_filter = ('is_favorite', 'tags')
    filter_horizontal = ('tags',)
    # Use the new Inlines to visualize graph data in Admin
    inlines = [CNSSpellbookNodeInline, CNSSpellbookWireInline]

    def node_count(self, obj):
        return obj.nodes.count()


class CNSSpellArgumentInline(admin.TabularInline):
    model = CNSSpellArgumentAssignment
    extra = 1


class CNSSpellTargetInline(admin.TabularInline):
    model = CNSSpellTarget
    extra = 0
    verbose_name = 'Pinned Target'


@admin.register(CNSSpell)
class CNSSpellAdmin(admin.ModelAdmin):
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
        CNSSpellArgumentInline,
        CNSSpellTargetInline,
        CNSSpellContextInline,
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
            # This fetches the variables defined in CNSSpellContextInline
            ctx = resolve_environment_context(spell_id=obj.id)

            # Pass BOTH the environment and the context to the renderer
            full_cmd_list = obj.get_full_command(
                environment=env, extra_context=ctx
            )

            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error: {str(e)}'


@admin.register(CNSHead)
class CNSHeadAdmin(admin.ModelAdmin):
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


@admin.register(CNSSpellbookNode)
class CNSSpellbookNodeAdmin(admin.ModelAdmin):
    """
    Instance-level configuration for Spells on a Graph.
    """

    list_display = ('id', 'spellbook', 'spell', 'distribution_mode', 'is_root')
    list_filter = ('spellbook', 'spell', 'distribution_mode')
    raw_id_fields = ('spellbook', 'spell', 'invoked_spellbook')
    inlines = [CNSSpellBookNodeContextInline]

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
            node_vars = CNSSpellBookNodeContext.objects.filter(node=obj)
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


admin.site.register(CNSHeadStatus)
admin.site.register(CNSSpawnStatus)
admin.site.register(CNSSpawn)
