import uuid

from django.db import models

from common.models import CreatedMixin, DefaultFieldsMixin, DescriptionMixin, ModifiedMixin, UUIDIdMixin


class ProjectEnvironment(models.Model):  # depreciated.
    """Configuration for where Executables may be run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, help_text="e.g., Mike Desktop 2024")

    # Paths
    project_root = models.CharField(max_length=500, help_text="Path to .uproject folder", blank=False, null=False)
    engine_root = models.CharField(max_length=500, help_text="Path to UE_5.6 folder", blank=False, null=False)
    build_root = models.CharField(max_length=500, help_text="Path to BUILD output", blank=False, null=False)
    project_name = models.CharField(max_length=100, help_text="The EXE Prefix (e.g., HSHVacancy)", blank=False,
                                    null=False)
    staging_dir = models.CharField(max_length=500, blank=True, null=True, help_text="Path to Staging output")

    agent_port = models.IntegerField(default=5005, help_text="Port the agent is listening on")
    is_active = models.BooleanField(default=False, help_text="Only one build environment can be active at a time.")

    def __str__(self):
        return f"{self.name} [{'ACTIVE' if self.is_active else 'OFF'}]"

    def save(self, *args, **kwargs):
        # Singleton logic: If this is active, deactivate others
        if self.is_active:
            ProjectEnvironment.objects.exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)


class TalosExecutableSwitch(DefaultFieldsMixin):
    """
    An option or flag for a Talos executable.
    """
    flag = models.CharField(max_length=255,
                            help_text="The actual flag e.g. '-clean', include equals or space if value is present.")
    value = models.CharField(max_length=255, blank=True, help_text="The value of the flag, if any.")


class TalosExecutableArgument(DefaultFieldsMixin):
    """An argument to be passed to the executable."""
    argument = models.CharField(max_length=500, help_text="The argument itself.")


class TalosExecutable(DefaultFieldsMixin, DescriptionMixin):
    """Reference to an executable usable by Talos."""
    INTERNAL_FUNCTION = 1  # use executable for the function name, which will be hard mapped in the spell caster.
    PYTHON = 2  # venv/Scripts/python.exe
    DJANGO = 3  # venv/Scripts/python.exe manage.py
    UNREAL_CMD = 4  # C:\\Program Files\\Epic Games\\UE_5.6/Engine/Binaries/Win64/UnrealEditor-Cmd.exe
    UNREAL_AUTOMATION_TOOL = 5  # C:\\Program Files\\Epic Games\\UE_5.6/Engine/Build/BatchFiles/RunUAT.bat
    UNREAL_STAGING = 6  # C:\steambuild\Windows\HSHVacancy.exe
    UNREAL_RELEASE_TEST = 7  # C:\steambuild\ReleaseTest\HSHVacancy.exe
    UNREAL_SHADER_TOOL = 8  # C:\\Program Files\\Epic Games\\UE_5.6/Engine/Binaries/Win64/ShaderPipelineCacheTools.exe
    VERSION_HANDLER = 9
    DEPLOY_RELEASE = 10

    working_path = models.CharField(max_length=500, help_text="Where to run the executable.", blank=True)
    executable = models.CharField(max_length=500, help_text="Full path to the executable, including filename.")
    log = models.CharField(max_length=500, help_text="Full path to the log, including filename.", blank=True)
    switches = models.ManyToManyField(TalosExecutableSwitch, blank=True)


class TalosExecutableArgumentAssignment(models.Model):
    executable = models.ForeignKey(TalosExecutable, on_delete=models.CASCADE)
    order = models.IntegerField(default=10)
    argument = models.ForeignKey(TalosExecutableArgument, on_delete=models.CASCADE)
    class Meta(object):
        ordering = ['order']


class TalosExecutableSupplementaryFileOrPath(DefaultFieldsMixin):
    """The name should be treated like a json field name. e.g. name=destination_file, path=c:/temp/temp.txt"""
    executable = models.ForeignKey(TalosExecutable, on_delete=models.CASCADE)
    path = models.CharField(max_length=500, help_text="Full path to the file.")
