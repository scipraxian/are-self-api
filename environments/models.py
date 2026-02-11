import uuid

from django.db import models, transaction

from common.constants import STANDARD_CHARFIELD_LENGTH
from common.models import (
    DefaultFieldsMixin,
    DescriptionMixin,
    NameMixin,
    UUIDIdMixin,
)

from .variable_renderer import VariableRenderer


class TalosExecutableSwitch(DefaultFieldsMixin):
    """
    An option or flag for a Talos executable.
    """

    flag = models.CharField(
        max_length=255,
        help_text=
        "The actual flag e.g. '-clean', include equals or space if value is present.",
    )
    value = models.CharField(max_length=255,
                             blank=True,
                             help_text='The value of the flag, if any.')


class TalosExecutableArgument(DefaultFieldsMixin):
    """An argument to be passed to the executable."""

    argument = models.CharField(max_length=500,
                                help_text='The argument itself.')


class TalosExecutable(DefaultFieldsMixin, DescriptionMixin):
    """Reference to an executable usable by Talos."""

    BEGIN_PLAY = 1
    PYTHON = 2  # venv/Scripts/python.exe
    DJANGO = 3  # venv/Scripts/python.exe manage.py
    UNREAL_CMD = 4  # C:\\Program Files\\Epic Games\\UE_5.6/Engine/Binaries/Win64/UnrealEditor-Cmd.exe
    UNREAL_AUTOMATION_TOOL = 5  # C:\\Program Files\\Epic Games\\UE_5.6/Engine/Build/BatchFiles/RunUAT.bat
    UNREAL_STAGING = 6  # C:\steambuild\Windows\HSHVacancy.exe
    UNREAL_RELEASE_TEST = 7  # C:\steambuild\ReleaseTest\HSHVacancy.exe
    UNREAL_SHADER_TOOL = 8  # C:\\Program Files\\Epic Games\\UE_5.6/Engine/Binaries/Win64/ShaderPipelineCacheTools.exe
    VERSION_HANDLER = 9
    DEPLOY_RELEASE = 10  # depreciated.

    internal = models.BooleanField(default=False,
                                   help_text='Internal Talos Python Function')
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
    switches = models.ManyToManyField(TalosExecutableSwitch, blank=True)

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


class TalosExecutableArgumentAssignment(models.Model):
    executable = models.ForeignKey(TalosExecutable, on_delete=models.CASCADE)
    order = models.IntegerField(default=10)
    argument = models.ForeignKey(TalosExecutableArgument,
                                 on_delete=models.CASCADE)

    class Meta(object):
        ordering = ['order']


class TalosExecutableSupplementaryFileOrPath(DefaultFieldsMixin):
    """The name should be treated like a json field name.
    e.g. name=destination_file, path=c:/temp/temp.txt"""

    executable = models.ForeignKey(TalosExecutable, on_delete=models.CASCADE)
    path = models.CharField(max_length=500, help_text='Full path to the file.')


class ProjectEnvironmentContextKey(NameMixin):
    pass


class ProjectEnvironmentStatus(NameMixin):
    """Lookup for Environment Status (e.g. Active, Archived)."""

    pass


class ProjectEnvironmentType(NameMixin):
    """Lookup for Environment Type (e.g. UE5, Unity, Custom)."""

    pass


class ProjectEnvironment(UUIDIdMixin, DefaultFieldsMixin, DescriptionMixin):
    """Defines the context for a specific Application/Project."""

    DEFAULT_ENVIRONMENT = uuid.UUID('44b23b94-6aae-4205-ae67-2f8c021c67aa')

    type = models.ForeignKey(ProjectEnvironmentType, on_delete=models.PROTECT)
    status = models.ForeignKey(ProjectEnvironmentStatus,
                               on_delete=models.PROTECT)
    available = models.BooleanField(default=False)
    selected = models.BooleanField(
        default=False,
        help_text='Only one environment can be selected at a time.',
    )

    def __str__(self):
        return f'{self.name} [{self.type.name}]'

    def save(self, *args, **kwargs):
        """Enforce Single Selection Logic"""
        if self.selected:
            with transaction.atomic():
                ProjectEnvironment.objects.filter(selected=True).exclude(
                    id=self.id).update(selected=False)
        super().save(*args, **kwargs)


class ContextVariable(models.Model):
    """Link table between Environment and Variables."""

    environment = models.ForeignKey(ProjectEnvironment,
                                    on_delete=models.CASCADE,
                                    related_name='contexts')
    key = models.ForeignKey(ProjectEnvironmentContextKey,
                            on_delete=models.CASCADE)
    value = models.TextField(blank=True)

    def __str__(self):
        return f'{self.environment.name} -> {self.key}'


class ProjectEnvironmentMixin(models.Model):
    environment = models.ForeignKey(ProjectEnvironment,
                                    on_delete=models.PROTECT,
                                    blank=True,
                                    null=True)

    class Meta:
        abstract = True
