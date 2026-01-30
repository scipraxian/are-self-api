"""Hydra Data Models."""

from django.db import models

from common.models import (
    CreatedMixin,
    DefaultFieldsMixin,
    DescriptionMixin,
    ModifiedMixin,
    NameMixin,
    UUIDIdMixin,
)
from environments.models import (
    TalosExecutable,
    TalosExecutableArgument,
    TalosExecutableSwitch,
)

from .constants import (
    ABORTED_LABEL,
    CREATED_LABEL,
    FAILED_LABEL,
    PENDING_LABEL,
    RUNNING_LABEL,
    SUCCESS_LABEL,
)

# --- DEFINITIONS (The Library) ---


class HydraStatusID(object):
    """
    Centralized Integer IDs for Status lookups.
    """

    CREATED = 1
    PENDING = 2
    RUNNING = 3
    SUCCESS = 4
    FAILED = 5
    ABORTED = 6


class HydraStatusTypeMixin(NameMixin):
    """Mixin to attach ID constants and Map to the Model Class."""

    IDs = HydraStatusID
    CREATED = HydraStatusID.CREATED
    PENDING = HydraStatusID.PENDING
    RUNNING = HydraStatusID.RUNNING
    SUCCESS = HydraStatusID.SUCCESS
    FAILED = HydraStatusID.FAILED
    ABORTED = HydraStatusID.ABORTED

    STATUS_MAP = {
        CREATED_LABEL: HydraStatusID.CREATED,
        PENDING_LABEL: HydraStatusID.PENDING,
        RUNNING_LABEL: HydraStatusID.RUNNING,
        SUCCESS_LABEL: HydraStatusID.SUCCESS,
        FAILED_LABEL: HydraStatusID.FAILED,
        ABORTED_LABEL: HydraStatusID.ABORTED,
    }

    class Meta:
        abstract = True


class HydraOutcomeActionID(object):
    """
    Centralized Integer IDs for Outcome Actions.
    """

    COPY = 1
    MOVE = 2
    VALIDATE_EXISTS = 3
    DELETE = 4
    ANALYZE = 5


class HydraDistributionModeID(object):
    """
    Centralized Integer IDs for Distribution Modes.
    """

    LOCAL_SERVER = 1
    ALL_ONLINE_AGENTS = 2
    ONE_AVAILABLE_AGENT = 3
    SPECIFIC_TARGETS = 4


class HydraDistributionMode(NameMixin, DescriptionMixin):
    """
    Lookup table for Distribution Modes.
    """

    IDs = HydraDistributionModeID

    class Meta:
        verbose_name = 'Hydra Distribution Mode'


class HydraSpell(DefaultFieldsMixin):
    """
    A configured action (Tool + specific Switches).
    """

    BEGIN_PLAY = 1

    talos_executable = models.ForeignKey(
        TalosExecutable, on_delete=models.PROTECT, default=1
    )
    switches = models.ManyToManyField(TalosExecutableSwitch, blank=True)
    distribution_mode = models.ForeignKey(
        HydraDistributionMode,
        on_delete=models.PROTECT,
        default=HydraDistributionModeID.LOCAL_SERVER,
    )


class HydraSpellTarget(models.Model):
    """
    Connecting table for Mode 4 (SPECIFIC_TARGETS).
    Links a Spell to specific 'Pinned' Agents.
    """

    spell = models.ForeignKey(
        HydraSpell, on_delete=models.CASCADE, related_name='specific_targets'
    )
    target = models.ForeignKey(
        'talos_agent.TalosAgentRegistry', on_delete=models.CASCADE
    )

    class Meta:
        unique_together = ('spell', 'target')
        verbose_name = 'Hydra Spell Target'

    def __str__(self):
        return f'{self.spell.name} -> {self.target}'


class HydraSpellArgumentAssignment(models.Model):
    spell = models.ForeignKey(HydraSpell, on_delete=models.CASCADE)
    order = models.IntegerField(default=10)
    argument = models.ForeignKey(
        TalosExecutableArgument, on_delete=models.CASCADE
    )

    class Meta(object):
        ordering = ['order']


class HydraOutcomeAction(NameMixin):
    """
    Lookup table for Outcome Actions.
    """

    IDs = HydraOutcomeActionID

    class Meta:
        verbose_name = 'Hydra Outcome Action'


class HydraSpellOutcomeConfig(DefaultFieldsMixin):
    """Configuration for expected outcomes."""

    spell = models.ForeignKey(
        'HydraSpell',
        on_delete=models.CASCADE,
        related_name='outcome_configs',
        null=True,
        blank=True,
    )
    action = models.ForeignKey(
        HydraOutcomeAction,
        on_delete=models.PROTECT,
        null=True,  # Allow null for migration compatibility if needed
        default=HydraOutcomeActionID.COPY,
    )

    source_path_template = models.CharField(
        max_length=500, help_text='Source path with {placeholders}', default=''
    )
    dest_path_template = models.CharField(
        max_length=500,
        blank=True,
        help_text='Destination path (if Copy/Move)',
        default='',
    )
    must_exist = models.BooleanField(
        default=True, help_text='Fail if source missing?'
    )

    def __str__(self):
        return f'{self.action} :: {self.source_path_template}'


class HydraSpellbook(UUIDIdMixin, DefaultFieldsMixin, DescriptionMixin):
    """
    The Container. Now supports a visual JSON layout.
    """

    name = models.CharField(max_length=255)
    ui_json = models.TextField(blank=True, default='{}')

    def __str__(self):
        return self.name


class HydraSpellbookNode(models.Model):
    """
    A visual instance of a Spell on the Graph.
    Allows the same Spell (e.g., 'Wait') to be used
    multiple times distinctively.
    """

    spellbook = models.ForeignKey(
        HydraSpellbook, on_delete=models.CASCADE, related_name='nodes'
    )
    spell = models.ForeignKey('HydraSpell', on_delete=models.CASCADE)
    ui_json = models.TextField(blank=True, default='{}')

    def __str__(self):
        return f'Node {self.id}: {self.spell.name}'


class HydraWireType(HydraStatusTypeMixin):
    """Status lookups for Wires."""

    TYPE_FLOW = 1
    TYPE_SUCCESS = 2
    TYPE_FAILURE = 3
    pass


class HydraSpellbookConnectionWire(ModifiedMixin):
    """
    The Wire. Connects two NODES (not spells).
    Trigger Condition: Fires when 'source' finishes with 'status'.
    """

    type = models.ForeignKey(
        HydraWireType, on_delete=models.PROTECT, default=HydraWireType.TYPE_FLOW
    )
    spellbook = models.ForeignKey(
        HydraSpellbook, on_delete=models.CASCADE, related_name='wires'
    )
    source = models.ForeignKey(
        HydraSpellbookNode,
        on_delete=models.CASCADE,
        related_name='outgoing_connections',
    )
    target = models.ForeignKey(
        HydraSpellbookNode,
        on_delete=models.CASCADE,
        related_name='incoming_connections',
    )

    class Meta:
        unique_together = ('spellbook', 'source', 'target')
        verbose_name = 'Wire / Connection'

    def __str__(self):
        return (
            f'{self.source.spell.name} '
            f'--[{self.type.name}]--> {self.target.spell.name}'
        )


# --- EXECUTION STATE (The Runtime) ---


class HydraSpawnStatus(HydraStatusTypeMixin):
    """Status lookups for Spawns."""

    pass


class HydraSpawn(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """Spellbook Instance."""

    spellbook = models.ForeignKey(
        HydraSpellbook, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.ForeignKey(HydraSpawnStatus, on_delete=models.PROTECT)

    context_data = models.TextField(
        blank=True, help_text='Serialized JSON context variables'
    )

    @property
    def is_active(self):
        """Returns True if the spawn is in a non-terminal state."""
        return self.status_id in [
            HydraSpawnStatus.CREATED,
            HydraSpawnStatus.PENDING,
            HydraSpawnStatus.RUNNING,
        ]

    def __str__(self):
        # Handle case where spellbook was deleted
        book_name = (
            self.spellbook.name if self.spellbook else 'Deleted Spellbook'
        )
        return f'Spawn {self.id} ({book_name})'


class HydraHeadStatus(HydraStatusTypeMixin):
    """Status lookups for Heads."""

    pass


class HydraHead(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """
    A single execution head (Process).
    """

    status = models.ForeignKey(HydraHeadStatus, on_delete=models.PROTECT)
    spawn = models.ForeignKey(
        HydraSpawn, related_name='heads', on_delete=models.CASCADE
    )
    node = models.ForeignKey(
        HydraSpellbookNode, on_delete=models.SET_NULL, null=True, blank=True
    )
    spell = models.ForeignKey(
        HydraSpell, on_delete=models.SET_NULL, null=True, blank=True
    )
    provenance = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='successors',
        help_text='The Head that triggered this execution.',
    )

    target = models.ForeignKey(
        'talos_agent.TalosAgentRegistry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    celery_task_id = models.UUIDField(null=True, blank=True)
    spell_log = models.TextField(blank=True)
    execution_log = models.TextField(blank=True)
    result_code = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['created']
