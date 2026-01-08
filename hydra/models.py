"""Hydra Data Models."""
from common.models import DescriptionMixin
from django.db import models
from environments.models import ProjectEnvironment
from common.models import (DefaultFieldsMixin, UUIDIdMixin, BigIdMixin,
                           NameMixin, CreatedMixin, ModifiedMixin)
from .constants import (CREATED_LABEL, PENDING_LABEL, RUNNING_LABEL,
                        SUCCESS_LABEL, FAILED_LABEL)

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


class HydraExecutable(DefaultFieldsMixin):
    """
    A base tool (e.g. Unreal Editor, Python).
    """
    slug = models.SlugField(unique=True,
                            help_text="Internal ID for bridge mapping")
    path_template = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "Hydra Executable"


class HydraSwitch(DefaultFieldsMixin):
    """
    An option or flag for a tool.
    """
    executable = models.ForeignKey(HydraExecutable,
                                   related_name='available_switches',
                                   on_delete=models.CASCADE)
    flag = models.CharField(max_length=100,
                            help_text="The actual flag e.g. '-clean'")
    value = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.executable.slug} :: {self.flag}"


class HydraSpell(DefaultFieldsMixin):
    """
    A configured action (Tool + specific Switches).
    """
    executable = models.ForeignKey(HydraExecutable, on_delete=models.PROTECT)
    active_switches = models.ManyToManyField(HydraSwitch, blank=True)
    order = models.PositiveIntegerField(
        default=0, help_text="Execution sequence (1, 2, 3...)")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"[{self.order}] {self.name}"


class HydraOutcomeAction(models.TextChoices):
    COPY = 'COPY', 'Copy'
    MOVE = 'MOVE', 'Move'
    VALIDATE_EXISTS = 'VALIDATE_EXISTS', 'Validate Exists'
    DELETE = 'DELETE', 'Delete'


class HydraSpellOutcomeConfig(DefaultFieldsMixin):
    """Configuration for expected outcomes."""
    spell = models.ForeignKey('HydraSpell',
                              on_delete=models.CASCADE,
                              related_name='outcome_configs',
                              null=True,
                              blank=True)
    action_type = models.CharField(max_length=20,
                                   choices=HydraOutcomeAction.choices,
                                   default=HydraOutcomeAction.COPY)
    source_path_template = models.CharField(
        max_length=500, help_text="Source path with {placeholders}", default='')
    dest_path_template = models.CharField(
        max_length=500,
        blank=True,
        help_text="Destination path (if Copy/Move)",
        default='')
    must_exist = models.BooleanField(default=True,
                                     help_text="Fail if source missing?")

    def __str__(self):
        return f"{self.action_type} :: {self.source_path_template}"


class HydraSpellbook(UUIDIdMixin, DefaultFieldsMixin, DescriptionMixin):
    """
    An ordered collection of Spells.
    Uses UUIDIdMixin to ensure IDs are URL-safe and distinct.
    """
    spells = models.ManyToManyField(HydraSpell, blank=True)
    outcomes = models.ManyToManyField(HydraSpellOutcomeConfig, blank=True)


# --- EXECUTION STATE (The Runtime) ---


class HydraStatusMixin(models.Model):
    """Mixin to attach ID constants and Map to the Model Class."""

    # Expose the Class Object for easy access (HydraHeadStatus.IDs.CREATED)
    IDs = HydraStatusID
    CREATED = HydraStatusID.CREATED
    PENDING = HydraStatusID.PENDING
    RUNNING = HydraStatusID.RUNNING
    SUCCESS = HydraStatusID.SUCCESS
    FAILED = HydraStatusID.FAILED

    STATUS_MAP = {
        CREATED_LABEL: HydraStatusID.CREATED,
        PENDING_LABEL: HydraStatusID.PENDING,
        RUNNING_LABEL: HydraStatusID.RUNNING,
        SUCCESS_LABEL: HydraStatusID.SUCCESS,
        FAILED_LABEL: HydraStatusID.FAILED,
    }

    class Meta:
        abstract = True


class HydraSpawnStatus(BigIdMixin, NameMixin, HydraStatusMixin):
    """Status lookups for Spawns."""
    pass


class HydraHeadStatus(BigIdMixin, NameMixin, HydraStatusMixin):
    """Status lookups for Heads."""
    pass


class HydraEnvironment(DefaultFieldsMixin):
    """
    Execution context mapping.
    """
    project_environment = models.ForeignKey(ProjectEnvironment,
                                            on_delete=models.PROTECT)
    executables = models.ManyToManyField(HydraExecutable, blank=True)


class HydraSpawn(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """
    An instance of a Spellbook executing in an Environment.
    """
    spellbook = models.ForeignKey(HydraSpellbook, on_delete=models.PROTECT)
    environment = models.ForeignKey(HydraEnvironment,
                                    on_delete=models.PROTECT,
                                    null=True)
    status = models.ForeignKey(HydraSpawnStatus, on_delete=models.PROTECT)

    context_data = models.TextField(
        blank=True, help_text="Serialized JSON context variables")

    def __str__(self):
        return f"Spawn {self.id} ({self.spellbook.name})"


class HydraHead(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """
    A single execution head (Process).
    """
    spawn = models.ForeignKey(HydraSpawn,
                              related_name='heads',
                              on_delete=models.CASCADE)
    spell = models.ForeignKey(HydraSpell, on_delete=models.PROTECT)

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


class HydraSpellOutcome(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """
    Outcome instance data.
    """
    name = models.CharField(max_length=254, db_index=True)
    outcome_config = models.CharField(blank=True, max_length=500)
