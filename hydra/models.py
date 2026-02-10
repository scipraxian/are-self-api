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


class HydraTag(NameMixin):
    """
    Native tagging system to avoid external dependency conflicts.
    """

    class Meta:
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'
        ordering = ['name']


class TagsAndFavoriteMixin(models.Model):
    is_favorite = models.BooleanField(default=False, db_index=True)
    tags = models.ManyToManyField(HydraTag, blank=True)

    class Meta:
        abstract = True


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


class HydraStatusTypeMixin(NameMixin):
    """Mixin to attach ID constants and Map to the Model Class."""

    IDs = HydraStatusID
    CREATED = HydraStatusID.CREATED
    PENDING = HydraStatusID.PENDING
    RUNNING = HydraStatusID.RUNNING
    SUCCESS = HydraStatusID.SUCCESS
    FAILED = HydraStatusID.FAILED
    ABORTED = HydraStatusID.ABORTED
    DELEGATED = HydraStatusID.DELEGATED
    STOPPING = HydraStatusID.STOPPING
    STOPPED = HydraStatusID.STOPPED
    IS_ALIVE_STATUS_LIST = HydraStatusID.IS_ALIVE_STATUS_LIST
    IS_TERMINAL_STATUS_LIST = HydraStatusID.IS_TERMINAL_STATUS_LIST

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


class HydraSpawnStatus(HydraStatusTypeMixin):
    """Status lookups for Spawns."""

    pass


class HydraHeadStatus(HydraStatusTypeMixin):
    """Status lookups for Heads."""

    pass


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


class HydraSpell(DefaultFieldsMixin, TagsAndFavoriteMixin):
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


class HydraSpellbook(
    UUIDIdMixin, DefaultFieldsMixin, DescriptionMixin, TagsAndFavoriteMixin
):
    """
    The Container. Now supports a visual JSON layout, Tags, and Favorites.
    """

    ui_json = models.TextField(blank=True, default='{}')

    def __str__(self):
        return self.name


class HydraSpellbookNode(models.Model):
    """
    A visual instance of a Spell on the Graph.
    Allows the same Spell (e.g., 'Wait') to be used
    multiple times distinctively.
    """

    is_root = models.BooleanField(default=False, db_index=True)
    spellbook = models.ForeignKey(
        HydraSpellbook, on_delete=models.CASCADE, related_name='nodes'
    )
    spell = models.ForeignKey(HydraSpell, on_delete=models.CASCADE)
    ui_json = models.TextField(blank=True, default='{}')

    invoked_spellbook = models.ForeignKey(
        HydraSpellbook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoking_nodes',
        help_text=(
            'If set, this Node acts as a container '
            'that executes this Spellbook.'
        ),
    )

    distribution_mode = models.ForeignKey(
        HydraDistributionMode, on_delete=models.SET_NULL, null=True
    )

    def __str__(self):
        return f'Node {self.id}: {self.spell.name}'


class HydraWireType(NameMixin):
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


class HydraSpawn(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """Spellbook Instance."""

    spellbook = models.ForeignKey(
        HydraSpellbook, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.ForeignKey(HydraSpawnStatus, on_delete=models.PROTECT)

    context_data = models.TextField(
        blank=True, help_text='Serialized JSON context variables'
    )

    parent_head = models.ForeignKey(
        'HydraHead',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_spawns',
        help_text='The Head (Node execution) in the Parent Graph that spawned this Sub-Graph.',
    )

    @property
    def is_active(self):  # legacy
        """Returns True if the spawn is in a non-terminal state."""
        return self.status_id in [
            HydraSpawnStatus.CREATED,
            HydraSpawnStatus.PENDING,
            HydraSpawnStatus.RUNNING,
        ]

    @property
    def is_alive(self):
        """Returns True if the spawn is in a non-terminal state."""
        return self.status_id in HydraSpawnStatus.IS_ALIVE_STATUS_LIST

    @property
    def is_dead(self):
        return self.status_id in HydraSpawnStatus.IS_TERMINAL_STATUS_LIST

    @property
    def is_queued(self):
        return self.status_id in [
            HydraSpawnStatus.PENDING,
            HydraSpawnStatus.CREATED,
        ]

    @property
    def is_stopping(self):
        return self.status_id == HydraSpawnStatus.STOPPING

    @property
    def ended_badly(self):
        return self.status_id in [
            HydraSpawnStatus.ABORTED,
            HydraSpawnStatus.FAILED,
        ]

    @property
    def ended_successfully(self):
        return self.status_id in [
            HydraSpawnStatus.SUCCESS,
            HydraSpawnStatus.STOPPED,
        ]

    @property
    def live_heads(self):
        return self.heads.filter(
            status__in=HydraHeadStatus.IS_ALIVE_STATUS_LIST
        ).exclude(spell_id=HydraSpell.BEGIN_PLAY)

    @property
    def finished_heads(self):
        return self.heads.filter(
            status__in=HydraHeadStatus.IS_TERMINAL_STATUS_LIST
        ).exclude(spell_id=HydraSpell.BEGIN_PLAY)

    @property
    def live_head_spawns(self):
        return HydraSpawn.objects.filter(
            parent_head__spawn=self,
            status__in=HydraSpawnStatus.IS_ALIVE_STATUS_LIST,
        )

    @property
    def finished_head_spawns(self):
        return HydraSpawn.objects.filter(
            parent_head__spawn=self,
            status__in=HydraSpawnStatus.IS_TERMINAL_STATUS_LIST,
        )


def __str__(self):
    # Handle case where spellbook was deleted
    book_name = self.spellbook.name if self.spellbook else 'Deleted Spellbook'
    return f'Spawn {self.id} ({book_name})'


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

    @property
    def is_active(self):  # TODO: DEPRECIATED LEGACY REMOVE, use is_alive.
        return self.status_id in [
            HydraHeadStatus.RUNNING,
            HydraHeadStatus.PENDING,
            HydraHeadStatus.STOPPING,
        ]

    @property
    def is_alive(self):
        return self.status_id in HydraHeadStatus.IS_ALIVE_STATUS_LIST

    @property
    def is_dead(self):
        return self.status_id in HydraHeadStatus.IS_TERMINAL_STATUS_LIST

    @property
    def is_queued(self):
        return self.status_id in [
            HydraHeadStatus.PENDING,
            HydraHeadStatus.CREATED,
        ]

    @property
    def is_stopping(self):
        return self.status_id == HydraHeadStatus.STOPPING

    @property
    def ended_badly(self):
        return self.status_id in [
            HydraHeadStatus.ABORTED,
            HydraHeadStatus.FAILED,
        ]

    @property
    def ended_successfully(self):
        return self.status_id in [
            HydraHeadStatus.SUCCESS,
            HydraHeadStatus.STOPPED,
        ]

    class Meta:
        ordering = ['created']
