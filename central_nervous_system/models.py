"""CNS Data Models."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from django.db import models

import environments
from common.constants import STANDARD_CHARFIELD_LENGTH
from common.models import (
    CreatedAndModifiedWithDelta,
    CreatedMixin,
    DefaultFieldsMixin,
    DescriptionMixin,
    ModifiedMixin,
    NameMixin,
    UUIDIdMixin,
)
from environments.models import (
    Executable,
    ExecutableArgument,
    ExecutableSwitch,
    ProjectEnvironmentMixin,
)
from environments.variable_renderer import VariableRenderer

from .constants import (
    ABORTED_LABEL,
    CREATED_LABEL,
    DELEGATED_LABEL,
    FAILED_LABEL,
    IS_ALIVE_LABEL,
    IS_TERMINAL_LABEL,
    PENDING_LABEL,
    RUNNING_LABEL,
    STOPPED_LABEL,
    STOPPING_LABEL,
    SUCCESS_LABEL,
)

# --- DEFINITIONS (The Library) ---


class CNSTag(NameMixin):
    """
    Native tagging system to avoid external dependency conflicts.
    """

    class Meta:
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'
        ordering = ['name']


class TagsAndFavoriteMixin(models.Model):
    is_favorite = models.BooleanField(default=False, db_index=True)
    tags = models.ManyToManyField(CNSTag, blank=True)

    class Meta:
        abstract = True


class CNSStatusID(object):
    """
    Centralized Integer IDs for Status lookups.
    """

    CREATED = 1
    PENDING = 2
    RUNNING = 3
    SUCCESS = 4
    FAILED = 5
    ABORTED = 6
    DELEGATED = 7
    STOPPING = 8
    STOPPED = 9
    IS_ALIVE_STATUS_LIST = [
        CREATED,
        DELEGATED,
        PENDING,
        RUNNING,
        STOPPING,
    ]
    IS_TERMINAL_STATUS_LIST = [FAILED, SUCCESS, ABORTED, STOPPED]


class CNSStatusTypeMixin(NameMixin):
    """Mixin to attach ID constants and Map to the Model Class."""

    IDs = CNSStatusID
    CREATED = CNSStatusID.CREATED
    PENDING = CNSStatusID.PENDING
    RUNNING = CNSStatusID.RUNNING
    SUCCESS = CNSStatusID.SUCCESS
    FAILED = CNSStatusID.FAILED
    ABORTED = CNSStatusID.ABORTED
    DELEGATED = CNSStatusID.DELEGATED
    STOPPING = CNSStatusID.STOPPING
    STOPPED = CNSStatusID.STOPPED
    IS_ALIVE_STATUS_LIST = CNSStatusID.IS_ALIVE_STATUS_LIST
    IS_TERMINAL_STATUS_LIST = CNSStatusID.IS_TERMINAL_STATUS_LIST

    STATUS_MAP = {
        CREATED_LABEL: CREATED,
        PENDING_LABEL: PENDING,
        RUNNING_LABEL: RUNNING,
        SUCCESS_LABEL: SUCCESS,
        FAILED_LABEL: FAILED,
        ABORTED_LABEL: ABORTED,
        STOPPING_LABEL: STOPPING,
        STOPPED_LABEL: STOPPED,
        DELEGATED_LABEL: DELEGATED,
        IS_ALIVE_LABEL: IS_ALIVE_STATUS_LIST,
        IS_TERMINAL_LABEL: IS_TERMINAL_STATUS_LIST,
    }

    class Meta:
        abstract = True


class SpikeTrainStatus(CNSStatusTypeMixin):
    """Status lookups for Spawns."""

    pass


class SpikeStatus(CNSStatusTypeMixin):
    """Status lookups for Heads."""

    pass


class CNSDistributionModeID(object):
    """
    Centralized Integer IDs for Distribution Modes.
    """

    LOCAL_SERVER = 1
    ALL_ONLINE_AGENTS = 2
    ONE_AVAILABLE_AGENT = 3
    SPECIFIC_TARGETS = 4


class CNSDistributionMode(NameMixin, DescriptionMixin):
    """
    Lookup table for Distribution Modes.
    """

    IDs = CNSDistributionModeID

    class Meta:
        verbose_name = 'CNS Distribution Mode'


class Effector(DefaultFieldsMixin, TagsAndFavoriteMixin, DescriptionMixin):
    """
    A configured action (Tool + specific Switches).
    """

    BEGIN_PLAY = 1
    LOGIC_GATE = 5
    LOGIC_RETRY = 6
    LOGIC_DELAY = 7
    FRONTAL_LOBE = 8
    DEBUG = 9

    executable = models.ForeignKey(
        Executable, on_delete=models.PROTECT, default=1
    )
    switches = models.ManyToManyField(ExecutableSwitch, blank=True)
    distribution_mode = models.ForeignKey(
        CNSDistributionMode,
        on_delete=models.PROTECT,
        default=CNSDistributionModeID.LOCAL_SERVER,
    )

    def get_full_command(
        self,
        environment: Optional['environments.models.ProjectEnvironment'] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Constructs the full command line [executable, arg1, arg2...]
        Resolves proper environment context and interpolates variables.
        """
        # 1. Resolve Global Context
        # Start with base wrapper context (e.g. hostname)
        context = VariableRenderer.extract_variables(None)

        # Update with Environment specific variables
        if environment:
            env_vars = VariableRenderer.extract_variables(environment)
            context.update(env_vars)

        # Apply runtime overrides (e.g. spike_train_id, spike_id)
        if extra_context:
            context.update(extra_context)

        # 2. Render Executable
        executable_path = self.executable.get_rendered_executable(
            environment
        )
        command_list = [executable_path]

        # 3. Gather and Render Arguments & Switches
        # We need to render them using the FULL context
        executable_args = (
            self.executable.executableargumentassignment_set.all()
        )
        spell_args = self.effectorargumentassignment_set.all()

        # Combine arguments, preserving order is tricky because they are separate querysets
        # But typically executable args come first in logic, though the model has 'order'
        # The legacy implementation merged them. Let's strictly follow the 'order' field if possible?
        # Actually legacy implementation did: list(executable_args) + list(spell_args)
        # We will stick to that behavior to be safe, but we should probably sort them by order if they share the same space?
        # Replicating legacy behavior:
        for assignment in list(executable_args) + list(spell_args):
            raw_arg = assignment.argument.argument.strip()
            resolved_arg = VariableRenderer.render_string(raw_arg, context)
            command_list.append(resolved_arg)

        # Switches
        executable_switches = self.executable.switches.all()
        spell_switches = self.switches.all()

        for switch in list(executable_switches) + list(spell_switches):
            flag = switch.flag.strip()
            value = switch.value.strip() if switch.value else ''
            # Legacy logic concatenated flag + value
            item = VariableRenderer.render_string(flag + value, context)
            command_list.append(item)

        return command_list


class EffectorContext(models.Model):
    effector = models.ForeignKey(Effector, on_delete=models.CASCADE)
    key = models.CharField(max_length=STANDARD_CHARFIELD_LENGTH)
    value = models.TextField(blank=True)


class EffectorTarget(models.Model):
    """
    Connecting table for Mode 4 (SPECIFIC_TARGETS).
    Links a Effector to specific 'Pinned' Agents.
    """

    effector = models.ForeignKey(
        Effector, on_delete=models.CASCADE, related_name='specific_targets'
    )
    target = models.ForeignKey(
        'peripheral_nervous_system.NerveTerminalRegistry',
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = ('effector', 'target')
        verbose_name = 'CNS Effector Target'

    def __str__(self):
        return f'{self.effector.name} -> {self.target}'


class EffectorArgumentAssignment(models.Model):
    effector = models.ForeignKey(Effector, on_delete=models.CASCADE)
    order = models.IntegerField(default=10)
    argument = models.ForeignKey(
        ExecutableArgument, on_delete=models.CASCADE
    )

    class Meta(object):
        ordering = ['order']

    def __str__(self):
        return f'{self.effector.name} -> {self.argument.argument}'


class NeuralPathway(
    UUIDIdMixin,
    DefaultFieldsMixin,
    DescriptionMixin,
    TagsAndFavoriteMixin,
    ProjectEnvironmentMixin,
):
    """
    The Container. Now supports a visual JSON layout, Tags, and Favorites.
    """

    # Contains the Thalamus Axon and Neuron.
    THALAMUS = UUID('04c3997f-d5f3-402f-952a-519bbd7e4dee')

    ui_json = models.TextField(blank=True, default='{}')

    def __str__(self):
        return self.name


class Neuron(ProjectEnvironmentMixin):
    """
    A visual instance of a Effector on the Graph.
    Allows the same Effector (e.g., 'Wait') to be used
    multiple times distinctively.
    """

    is_root = models.BooleanField(default=False, db_index=True)
    pathway = models.ForeignKey(
        NeuralPathway, on_delete=models.CASCADE, related_name='neurons'
    )
    effector = models.ForeignKey(Effector, on_delete=models.CASCADE)
    ui_json = models.TextField(blank=True, default='{}')

    invoked_pathway = models.ForeignKey(
        NeuralPathway,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoking_nodes',
        help_text=(
            'If set, this Node acts as a container '
            'that executes this NeuralPathway.'
        ),
    )

    distribution_mode = models.ForeignKey(
        CNSDistributionMode, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f'Neuron {self.id}: {self.effector.name}'


class NeuronContext(models.Model):
    neuron = models.ForeignKey(Neuron, on_delete=models.CASCADE)
    key = models.CharField(max_length=STANDARD_CHARFIELD_LENGTH)
    value = models.TextField(blank=True)


class AxonType(NameMixin):
    """Status lookups for Wires."""

    TYPE_FLOW = 1
    TYPE_SUCCESS = 2
    TYPE_FAILURE = 3
    pass


class Axon(ModifiedMixin):
    """
    The Wire. Connects two NODES (not effectors).
    Trigger Condition: Fires when 'source' finishes with 'status'.
    """

    type = models.ForeignKey(
        AxonType, on_delete=models.PROTECT, default=AxonType.TYPE_FLOW
    )
    pathway = models.ForeignKey(
        NeuralPathway, on_delete=models.CASCADE, related_name='axons'
    )
    source = models.ForeignKey(
        Neuron,
        on_delete=models.CASCADE,
        related_name='outgoing_connections',
    )
    target = models.ForeignKey(
        Neuron,
        on_delete=models.CASCADE,
        related_name='incoming_connections',
    )

    class Meta:
        unique_together = ('pathway', 'source', 'target')
        verbose_name = 'Wire / Connection'

    def __str__(self):
        return (
            f'{self.source.effector.name} '
            f'--[{self.type.name}]--> {self.target.effector.name}'
        )


# --- EXECUTION STATE (The Runtime) ---


class SpikeTrain(
    UUIDIdMixin, CreatedAndModifiedWithDelta, ProjectEnvironmentMixin
):
    """NeuralPathway Instance."""

    pathway = models.ForeignKey(
        NeuralPathway, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.ForeignKey(SpikeTrainStatus, on_delete=models.PROTECT)
    cerebrospinal_fluid = models.JSONField(default=dict, blank=True)

    parent_spike = models.ForeignKey(
        'Spike',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_trains',
        help_text='The Spike (Node execution) in the Parent Graph that spawned this Sub-Graph.',
    )

    @property
    def is_active(self):  # legacy
        """Returns True if the spike_train is in a non-terminal state."""
        return self.status_id in [
            SpikeTrainStatus.CREATED,
            SpikeTrainStatus.PENDING,
            SpikeTrainStatus.RUNNING,
        ]

    @property
    def is_alive(self):
        """Returns True if the spike_train is in a non-terminal state."""
        return self.status_id in SpikeTrainStatus.IS_ALIVE_STATUS_LIST

    @property
    def is_dead(self):
        return self.status_id in SpikeTrainStatus.IS_TERMINAL_STATUS_LIST

    @property
    def is_queued(self):
        return self.status_id in [
            SpikeTrainStatus.PENDING,
            SpikeTrainStatus.CREATED,
        ]

    @property
    def is_stopping(self):
        return self.status_id == SpikeTrainStatus.STOPPING

    @property
    def ended_badly(self):
        return self.status_id in [
            SpikeTrainStatus.ABORTED,
            SpikeTrainStatus.FAILED,
        ]

    @property
    def ended_successfully(self):
        return self.status_id in [
            SpikeTrainStatus.SUCCESS,
            SpikeTrainStatus.STOPPED,
        ]

    @property
    def live_spikes(self):
        return self.spikes.filter(
            status__in=SpikeStatus.IS_ALIVE_STATUS_LIST
        ).exclude(effector_id=Effector.BEGIN_PLAY)

    @property
    def finished_spikes(self):
        return self.spikes.filter(
            status__in=SpikeStatus.IS_TERMINAL_STATUS_LIST
        ).exclude(effector_id=Effector.BEGIN_PLAY)

    @property
    def live_spike_trains(self):
        return SpikeTrain.objects.filter(
            parent_spike__spike_train=self,
            status__in=SpikeTrainStatus.IS_ALIVE_STATUS_LIST,
        )

    @property
    def finished_spike_trains(self):
        return SpikeTrain.objects.filter(
            parent_spike__spike_train=self,
            status__in=SpikeTrainStatus.IS_TERMINAL_STATUS_LIST,
        )

    def __str__(self):
        # Handle case where pathway was deleted
        book_name = (
            self.pathway.name if self.pathway else 'Deleted NeuralPathway'
        )
        return f'SpikeTrain {self.id} ({book_name})'


class Spike(UUIDIdMixin, CreatedAndModifiedWithDelta):
    """A single execution spike (Process)."""

    status = models.ForeignKey(SpikeStatus, on_delete=models.PROTECT)
    spike_train = models.ForeignKey(
        SpikeTrain, related_name='spikes', on_delete=models.CASCADE
    )
    neuron = models.ForeignKey(
        Neuron, on_delete=models.SET_NULL, null=True, blank=True
    )
    effector = models.ForeignKey(
        Effector, on_delete=models.SET_NULL, null=True, blank=True
    )
    provenance = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='successors',
        help_text='The Spike that triggered this execution.',
    )

    target = models.ForeignKey(
        'peripheral_nervous_system.NerveTerminalRegistry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    celery_task_id = models.UUIDField(null=True, blank=True)
    application_log = models.TextField(blank=True)
    execution_log = models.TextField(blank=True)
    result_code = models.IntegerField(null=True, blank=True)

    axoplasm = models.JSONField(default=dict, blank=True)

    @property
    def is_active(self):  # TODO: DEPRECIATED LEGACY REMOVE, use is_alive.
        return self.status_id in [
            SpikeStatus.RUNNING,
            SpikeStatus.PENDING,
            SpikeStatus.STOPPING,
        ]

    @property
    def is_alive(self):
        return self.status_id in SpikeStatus.IS_ALIVE_STATUS_LIST

    @property
    def is_dead(self):
        return self.status_id in SpikeStatus.IS_TERMINAL_STATUS_LIST

    @property
    def is_queued(self):
        return self.status_id in [
            SpikeStatus.PENDING,
            SpikeStatus.CREATED,
        ]

    @property
    def is_stopping(self):
        return self.status_id == SpikeStatus.STOPPING

    @property
    def ended_badly(self):
        return self.status_id in [
            SpikeStatus.ABORTED,
            SpikeStatus.FAILED,
        ]

    @property
    def ended_successfully(self):
        return self.status_id in [
            SpikeStatus.SUCCESS,
            SpikeStatus.STOPPED,
        ]

    @property
    def timestamp_str(self):
        return self.created.strftime('%H:%M:%S') if self.created else ''

    class Meta:
        ordering = ['created']
