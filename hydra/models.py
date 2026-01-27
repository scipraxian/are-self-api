"""Hydra Data Models."""

from django.db import models

from common.models import (
    BigIdMixin,
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


class HydraOutcomeActionID(object):
    """
    Centralized Integer IDs for Outcome Actions.
    """

    COPY = 1
    MOVE = 2
    VALIDATE_EXISTS = 3
    DELETE = 4
    ANALYZE = 5


class HydraExecutableType(DefaultFieldsMixin):  # depreciated
    """
    Centralized Integer IDs for Executable Types.
    """

    LOCAL_PYTHON = 1
    REMOTE_PYTHON = 2
    LOCAL_POPEN = 3
    REMOTE_POPEN = 4


class HydraDistributionModeID(object):
    """
    Centralized Integer IDs for Distribution Modes.
    """

    LOCAL_SERVER = 1
    ALL_ONLINE_AGENTS = 2
    ONE_AVAILABLE_AGENT = 3
    SPECIFIC_TARGETS = 4


class HydraDistributionMode(BigIdMixin, NameMixin, DescriptionMixin):
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

    talos_executable = models.ForeignKey(
        TalosExecutable, on_delete=models.PROTECT, default=1
    )
    switches = models.ManyToManyField(TalosExecutableSwitch, blank=True)
    distribution_mode = models.ForeignKey(
        HydraDistributionMode,
        on_delete=models.PROTECT,
        default=HydraDistributionModeID.LOCAL_SERVER,
    )

    # LEGACY
    order = models.PositiveIntegerField(
        default=0, help_text='Execution sequence (1, 2, 3...)'
    )  # TODO: DEPRECIATED

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'[{self.order}] {self.name}'


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


class HydraOutcomeAction(BigIdMixin, NameMixin):
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
    An ordered collection of Spells.
    Uses UUIDIdMixin to ensure IDs are URL-safe and distinct.
    """

    spells = models.ManyToManyField(HydraSpell, blank=True)


# --- EXECUTION STATE (The Runtime) ---


class HydraStatusMixin(models.Model):
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


class HydraSpawnStatus(BigIdMixin, NameMixin, HydraStatusMixin):
    """Status lookups for Spawns."""

    pass


class HydraHeadStatus(BigIdMixin, NameMixin, HydraStatusMixin):
    """Status lookups for Heads."""

    pass


class HydraSpawn(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """
    An instance of a Spellbook executing in an Environment.
    """

    spellbook = models.ForeignKey(HydraSpellbook, on_delete=models.PROTECT)
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
        return f'Spawn {self.id} ({self.spellbook.name})'


class HydraHead(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """
    A single execution head (Process).
    """

    spawn = models.ForeignKey(
        HydraSpawn, related_name='heads', on_delete=models.CASCADE
    )
    spell = models.ForeignKey(HydraSpell, on_delete=models.PROTECT)

    target = models.ForeignKey(
        'talos_agent.TalosAgentRegistry',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )

    celery_task_id = models.UUIDField(null=True, blank=True)
    status = models.ForeignKey(HydraHeadStatus, on_delete=models.PROTECT)

    spell_log = models.TextField(blank=True)
    execution_log = models.TextField(blank=True)
    result_code = models.IntegerField(null=True, blank=True)


class HydraResult(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """
    The output artifact or report of a Head execution.
    """

    head = models.ForeignKey(HydraHead, on_delete=models.CASCADE)
    spell = models.ForeignKey(HydraSpell, on_delete=models.PROTECT)
    report = models.CharField(max_length=500, blank=True)
