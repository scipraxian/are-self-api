from rest_framework import serializers

from common.constants import ALL_FIELDS
from central_nervous_system.constants import ENVIRONMENT_KEY

from .models import (
    ContextVariable,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
    TalosExecutable,
    TalosExecutableArgument,
    TalosExecutableArgumentAssignment,
    TalosExecutableSupplementaryFileOrPath,
    TalosExecutableSwitch,
)


class ProjectEnvironmentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectEnvironmentType
        fields = ALL_FIELDS


class ProjectEnvironmentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectEnvironmentStatus
        fields = ALL_FIELDS


class ProjectEnvironmentContextKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectEnvironmentContextKey
        fields = ALL_FIELDS


class ContextVariableSerializer(serializers.ModelSerializer):
    """
    Writable. Used to update environment variables.
    """

    key_name = serializers.CharField(source='key.name', read_only=True)

    class Meta:
        model = ContextVariable
        fields = ALL_FIELDS


class ProjectEnvironmentSerializer(serializers.ModelSerializer):
    """
    Main Environment serializer.
    'contexts' is read-only nested for display.
    """

    type_name = serializers.CharField(source='type.name', read_only=True)
    status_name = serializers.CharField(source='status.name', read_only=True)
    contexts = ContextVariableSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectEnvironment
        fields = ALL_FIELDS


class TalosExecutableSwitchSerializer(serializers.ModelSerializer):
    class Meta:
        model = TalosExecutableSwitch
        fields = ALL_FIELDS


class TalosExecutableArgumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TalosExecutableArgument
        fields = ALL_FIELDS


class TalosExecutableArgumentAssignmentSerializer(serializers.ModelSerializer):
    argument_detail = TalosExecutableArgumentSerializer(
        source='argument', read_only=True
    )

    class Meta:
        model = TalosExecutableArgumentAssignment
        fields = ALL_FIELDS


class TalosExecutableSupplementaryFileOrPathSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = TalosExecutableSupplementaryFileOrPath
        fields = ALL_FIELDS


class TalosExecutableSerializer(serializers.ModelSerializer):
    """
    Executable definition.
    Uses ALL_FIELDS for model data, plus computed fields for UI convenience.
    """

    # Computed / Nested Display Fields
    switches_detail = TalosExecutableSwitchSerializer(
        source='switches', many=True, read_only=True
    )
    argument_assignments = TalosExecutableArgumentAssignmentSerializer(
        source='talosexecutableargumentassignment_set',
        many=True,
        read_only=True,
    )
    files = TalosExecutableSupplementaryFileOrPathSerializer(
        source='talosexecutablesupplementaryfileorpath_set',
        many=True,
        read_only=True,
    )
    rendered_executable = serializers.SerializerMethodField()

    class Meta:
        model = TalosExecutable
        fields = ALL_FIELDS  # Includes standard model fields + the ones defined above

    def get_rendered_executable(self, obj) -> str:
        """
        Returns the executable path with variables interpolated.
        """
        env = self.context.get(ENVIRONMENT_KEY)
        return obj.get_rendered_executable(environment=env)
