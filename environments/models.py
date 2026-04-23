import uuid

from django.db import models, transaction

from common.models import (
    DefaultFieldsMixin,
    DescriptionMixin,
    NameMixin,
    UUIDIdMixin,
)
from neuroplasticity.genome_mixin import GenomeOwnedMixin

from .variable_renderer import VariableRenderer


class ExecutableSwitch(UUIDIdMixin, DefaultFieldsMixin, GenomeOwnedMixin):
    """An option or flag for an executable."""

    flag = models.CharField(
        max_length=255,
        help_text="The actual flag e.g. '-clean', include equals or space if value is present.",
    )
    value = models.CharField(
        max_length=255, blank=True, help_text='The value of the flag, if any.'
    )


class ExecutableArgument(UUIDIdMixin, DefaultFieldsMixin, GenomeOwnedMixin):
    """An argument to be passed to the executable."""

    argument = models.CharField(
        max_length=500, help_text='The argument itself.'
    )

    def __str__(self):
        return f'{self.name} - {self.argument}'


class Executable(
    UUIDIdMixin, DefaultFieldsMixin, DescriptionMixin, GenomeOwnedMixin
):
    """Reference to an executable usable by Are-Self."""

    BEGIN_PLAY = uuid.UUID('974ed732-6f2d-47f4-9482-18d17c73086e')
    PYTHON = uuid.UUID(
        '558806d7-d009-4e89-8e4e-86979dcd0594'
    )  # venv/Scripts/python.exe
    DJANGO = uuid.UUID(
        '11915177-a32b-4883-8c9f-e137c528c20d'
    )  # venv/Scripts/python.exe manage.py

    internal = models.BooleanField(
        default=False, help_text='Internal Python Function'
    )
    working_path = models.CharField(
        max_length=500,
        help_text='[DEPRECATED/UNUSED] Where to run the executable.',
        blank=True,
    )
    executable = models.CharField(
        max_length=500,
        help_text='Full path to the executable, including filename.',
    )
    log = models.CharField(
        max_length=500,
        help_text='Full path to the log, including filename.',
        blank=True,
    )
    switches = models.ManyToManyField(ExecutableSwitch, blank=True)

    def get_rendered_executable(self, environment=None) -> str:
        """
        Returns the executable path with variables interpolated.
        """
        # 1. Base Context (Hostname, etc)
        context = VariableRenderer.extract_variables(None)

        # 2. Environment Overrides
        if environment:
            env_vars = VariableRenderer.extract_variables(environment)
            context.update(env_vars)

        return VariableRenderer.render_string(self.executable, context)


class ExecutableArgumentAssignment(UUIDIdMixin):
    executable = models.ForeignKey(Executable, on_delete=models.CASCADE)
    order = models.IntegerField(default=10)
    argument = models.ForeignKey(ExecutableArgument, on_delete=models.CASCADE)

    class Meta(object):
        ordering = ['order']

    def __str__(self):
        return f'{self.executable} - {self.argument}'


class ExecutableSupplementaryFileOrPath(DefaultFieldsMixin):
    """The name should be treated like a json field name.
    e.g. name=destination_file, path=c:/temp/temp.txt"""

    executable = models.ForeignKey(Executable, on_delete=models.CASCADE)
    path = models.CharField(max_length=500, help_text='Full path to the file.')


class ProjectEnvironmentContextKey(UUIDIdMixin, NameMixin):
    pass


class ProjectEnvironmentStatus(UUIDIdMixin, NameMixin):
    """Lookup for Environment Status (e.g. Active, Archived)."""

    pass


class ProjectEnvironmentType(UUIDIdMixin, NameMixin):
    """Lookup for Environment Type (e.g. UE5, Unity, Custom)."""

    pass


class ProjectEnvironment(
    UUIDIdMixin, DefaultFieldsMixin, DescriptionMixin, GenomeOwnedMixin
):
    """Defines the context for a specific Application/Project."""

    DEFAULT_ENVIRONMENT = uuid.UUID('b7e4c2a1-3f8d-4a9e-9c1f-2d5a8b6f4e21')

    type = models.ForeignKey(ProjectEnvironmentType, on_delete=models.PROTECT)
    status = models.ForeignKey(
        ProjectEnvironmentStatus, on_delete=models.PROTECT
    )
    available = models.BooleanField(default=False)
    selected = models.BooleanField(
        default=False,
        help_text='Only one environment can be selected at a time.',
    )
    default_iteration_definition = models.ForeignKey(
        'temporal_lobe.IterationDefinition',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f'{self.name} [{self.type.name}]'

    def save(self, *args, **kwargs):
        """Enforce Single Selection Logic"""
        if self.selected:
            with transaction.atomic():
                ProjectEnvironment.objects.filter(selected=True).exclude(
                    id=self.id
                ).update(selected=False)
        super().save(*args, **kwargs)


class ContextVariable(UUIDIdMixin):
    """Link table between Environment and Variables."""

    environment = models.ForeignKey(
        ProjectEnvironment, on_delete=models.CASCADE, related_name='contexts'
    )
    key = models.ForeignKey(
        ProjectEnvironmentContextKey, on_delete=models.CASCADE
    )
    value = models.TextField(blank=True)

    def __str__(self):
        return f'{self.environment.name} -> {self.key}'


class ProjectEnvironmentMixin(models.Model):
    environment = models.ForeignKey(
        ProjectEnvironment, on_delete=models.SET_NULL, blank=True, null=True
    )

    class Meta:
        abstract = True
