from django.contrib import admin

from central_nervous_system.utils import (
    get_active_environment,
    resolve_environment_context,
)
from environments.models import ProjectEnvironment

from .models import (
    Axon,
    CNSDistributionMode,
    CNSTag,
    Effector,
    EffectorArgumentAssignment,
    EffectorContext,
    EffectorTarget,
    NeuralPathway,
    Neuron,
    NeuronContext,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)


class EffectorContextInline(admin.TabularInline):
    """Configuration: Default variables for this Spell."""

    model = EffectorContext
    extra = 1
    verbose_name = 'Default Variable'
    verbose_name_plural = 'Default Variables (Tier 1)'


class EffectorBookNodeContextInline(admin.TabularInline):
    """Configuration: Overrides for this specific Node instance."""

    model = NeuronContext
    extra = 1
    verbose_name = 'Override Variable'
    verbose_name_plural = 'Override Variables (Tier 2)'


@admin.register(CNSDistributionMode)
class CNSDistributionModeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


class CNSNeuralPathwayNodeInline(admin.TabularInline):
    """Shows the neurons contained in this book."""

    model = Neuron
    extra = 0
    verbose_name = 'Graph Node'
    readonly_fields = ('ui_json', 'is_root')
    fk_name = 'pathway'


class CNSNeuralPathwayWireInline(admin.TabularInline):
    """Shows the axons."""

    model = Axon
    extra = 0
    fk_name = 'pathway'
    verbose_name = 'Wire'


@admin.register(CNSTag)
class CNSTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(NeuralPathway)
class CNSNeuralPathwayAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'is_favorite', 'created', 'node_count')
    list_filter = ('is_favorite', 'tags')
    filter_horizontal = ('tags',)
    # Use the new Inlines to visualize graph data in Admin
    inlines = [CNSNeuralPathwayNodeInline, CNSNeuralPathwayWireInline]

    def node_count(self, obj):
        return obj.neurons.count()


class EffectorArgumentInline(admin.TabularInline):
    model = EffectorArgumentAssignment
    extra = 1


class EffectorTargetInline(admin.TabularInline):
    model = EffectorTarget
    extra = 0
    verbose_name = 'Pinned Target'


@admin.register(Effector)
class EffectorAdmin(admin.ModelAdmin):
    # FIXED: Removed 'order' from list_display
    list_display = (
        'name',
        'executable',
        'distribution_mode',
        'resolved_command_preview',
    )
    list_filter = ('distribution_mode', 'executable')
    filter_horizontal = ('switches',)
    inlines = [
        EffectorArgumentInline,
        EffectorTargetInline,
        EffectorContextInline,
    ]
    readonly_fields = ('resolved_command_preview',)

    fieldsets = (
        ('Identity', {
            'fields': ('name', 'resolved_command_preview')
        }),
        ('Distribution Strategy', {
            'fields': ('distribution_mode',)
        }),
        ('Configuration', {
            'fields': ('executable', 'switches')
        }),
    )

    def resolved_command_preview(self, obj):
        try:
            # [FIX] Fetch the currently selected environment for context
            env = ProjectEnvironment.objects.filter(selected=True).first()

            # [FIX] Resolve Tier 1 Defaults (Effector Context)
            # This fetches the variables defined in EffectorContextInline
            ctx = resolve_environment_context(effector_id=obj.id)

            # Pass BOTH the environment and the context to the renderer
            full_cmd_list = obj.get_full_command(environment=env,
                                                 extra_context=ctx)

            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error: {str(e)}'


@admin.register(Spike)
class SpikeAdmin(admin.ModelAdmin):
    # Added 'neuron' and 'provenance' to list for debugging
    list_display = (
        'id',
        'effector_name',
        'status',
        'created',
        'neuron',
        'provenance',
    )
    list_filter = ('status', 'effector__name')
    readonly_fields = (
        'celery_task_id',
        'application_log',
        'execution_log',
        'resolved_command_preview',
    )

    def effector_name(self, obj):
        return obj.effector.name

    def resolved_command_preview(self, obj):
        try:
            if not obj.effector:
                return '-'

            env = get_active_environment(obj)
            ctx = resolve_environment_context(spike_id=obj.id)

            full_cmd_list = obj.effector.get_full_command(environment=env,
                                                          extra_context=ctx)
            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error: {str(e)}'


@admin.register(Neuron)
class CNSNeuralPathwayNodeAdmin(admin.ModelAdmin):
    """
    Instance-level configuration for Effectors on a Graph.
    """

    list_display = ('id', 'pathway', 'effector', 'distribution_mode', 'is_root')
    list_filter = ('pathway', 'effector', 'distribution_mode')
    raw_id_fields = ('pathway', 'effector', 'invoked_pathway')
    inlines = [EffectorBookNodeContextInline]

    # [NEW] Add readonly field
    readonly_fields = ('resolved_command_preview',)

    fieldsets = (
        ('Graph Placement', {
            'fields': ('pathway', 'ui_json', 'is_root')
        }),
        (
            'Execution Logic',
            {
                'fields': ('effector', 'invoked_pathway', 'distribution_mode'),
                'description':
                    "If Distribution Mode is empty, the Effector's default strategy will be used.",
            },
        ),
        # [NEW] Preview Section
        (
            'Context Preview',
            {
                'fields': ('resolved_command_preview',),
                'description':
                    'Shows the command as it would execute in the currently Selected Environment, applying Effector Defaults and Node Overrides.',
            },
        ),
    )

    def resolved_command_preview(self, obj):
        try:
            if not obj.effector:
                return 'No Effector Assigned'

            # 1. Base Env
            env = ProjectEnvironment.objects.filter(selected=True).first()

            # 2. Effector Defaults (Tier 1)
            # We use the utility to get Env + Effector vars first
            ctx = resolve_environment_context(effector_id=obj.effector.id)

            # 3. Node Overrides (Tier 2)
            # Manually apply these since resolve_environment_context doesn't take node_id directly yet
            node_vars = NeuronContext.objects.filter(neuron=obj)
            for var in node_vars:
                if var.key:
                    ctx[var.key] = var.value

            # 4. Render
            full_cmd_list = obj.effector.get_full_command(environment=env,
                                                          extra_context=ctx)
            return ' '.join(full_cmd_list)
        except Exception as e:
            return f'Error generating preview: {str(e)}'


admin.site.register(SpikeStatus)
admin.site.register(SpikeTrainStatus)



@admin.register(SpikeTrain)
class SpikeTrainAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'status',
        'created',
    )
