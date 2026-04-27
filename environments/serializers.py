from rest_framework import serializers

from central_nervous_system.constants import ENVIRONMENT_KEY
from common.constants import ALL_FIELDS
from neuroplasticity.serializer_mixins import (
    GenomeDisplayMixin,
    GenomeOwnedSerializerMixin,
    GenomeWritableMixin,
)

from .models import (
    ContextVariable,
    Executable,
    ExecutableArgument,
    ExecutableArgumentAssignment,
    ExecutableSupplementaryFileOrPath,
    ExecutableSwitch,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
    ProjectEnvironmentStatus,
)


class ProjectEnvironmentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectEnvironmentStatus
        fields = ALL_FIELDS


class ProjectEnvironmentContextKeySerializer(
    GenomeOwnedSerializerMixin,
    GenomeWritableMixin,
    GenomeDisplayMixin,
    serializers.ModelSerializer,
):
    class Meta:
        model = ProjectEnvironmentContextKey
        fields = ALL_FIELDS


class ContextVariableSerializer(
    GenomeOwnedSerializerMixin,
    GenomeWritableMixin,
    GenomeDisplayMixin,
    serializers.ModelSerializer,
):
    """
    Writable. Used to update environment variables.
    """

    key_name = serializers.CharField(source='key.name', read_only=True)

    class Meta:
        model = ContextVariable
        fields = ALL_FIELDS


class ProjectEnvironmentSerializer(
    GenomeOwnedSerializerMixin,
    GenomeWritableMixin,
    GenomeDisplayMixin,
    serializers.ModelSerializer,
):
    """
    Main Environment serializer.
    'contexts' is read-only nested for display.
    """

    status_name = serializers.CharField(source='status.name', read_only=True)
    contexts = ContextVariableSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectEnvironment
        fields = ALL_FIELDS


class ExecutableSwitchSerializer(
    GenomeWritableMixin, GenomeDisplayMixin, serializers.ModelSerializer
):
    class Meta:
        model = ExecutableSwitch
        fields = ALL_FIELDS


class ExecutableArgumentSerializer(
    GenomeOwnedSerializerMixin,
    GenomeWritableMixin,
    GenomeDisplayMixin,
    serializers.ModelSerializer,
):
    class Meta:
        model = ExecutableArgument
        fields = ALL_FIELDS


class ExecutableArgumentAssignmentSerializer(
    GenomeOwnedSerializerMixin,
    GenomeWritableMixin,
    GenomeDisplayMixin,
    serializers.ModelSerializer,
):
    argument_detail = ExecutableArgumentSerializer(
        source='argument', read_only=True
    )

    class Meta:
        model = ExecutableArgumentAssignment
        fields = ALL_FIELDS


class ExecutableSupplementaryFileOrPathSerializer(
    GenomeWritableMixin, GenomeDisplayMixin, serializers.ModelSerializer
):
    class Meta:
        model = ExecutableSupplementaryFileOrPath
        fields = ALL_FIELDS


class ExecutableSerializer(
    GenomeOwnedSerializerMixin,
    GenomeWritableMixin,
    GenomeDisplayMixin,
    serializers.ModelSerializer,
):
    """
    Executable definition.
    Uses ALL_FIELDS for model data, plus computed fields for UI convenience.
    """

    # Computed / Nested Display Fields
    switches_detail = ExecutableSwitchSerializer(
        source='switches', many=True, read_only=True
    )
    argument_assignments = ExecutableArgumentAssignmentSerializer(
        source='executableargumentassignment_set',
        many=True,
        read_only=True,
    )
    files = ExecutableSupplementaryFileOrPathSerializer(
        source='executablesupplementaryfileorpath_set',
        many=True,
        read_only=True,
    )
    rendered_executable = serializers.SerializerMethodField()

    class Meta:
        model = Executable
        fields = ALL_FIELDS  # Includes standard model fields + the ones defined above

    def get_rendered_executable(self, obj) -> str:
        """
        Returns the executable path with variables interpolated.
        """
        env = self.context.get(ENVIRONMENT_KEY)
        return obj.get_rendered_executable(environment=env)
