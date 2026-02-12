from rest_framework import serializers

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
from .variable_renderer import VariableRenderer


class ProjectEnvironmentTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProjectEnvironmentType
        fields = '__all__'


class ProjectEnvironmentStatusSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProjectEnvironmentStatus
        fields = '__all__'


class ProjectEnvironmentContextKeySerializer(serializers.ModelSerializer):

    class Meta:
        model = ProjectEnvironmentContextKey
        fields = '__all__'


class ContextVariableSerializer(serializers.ModelSerializer):
    key_name = serializers.CharField(source='key.name', read_only=True)

    class Meta:
        model = ContextVariable
        fields = ['id', 'environment', 'key', 'key_name', 'value']


class ProjectEnvironmentSerializer(serializers.ModelSerializer):
    type_name = serializers.CharField(source='type.name', read_only=True)
    status_name = serializers.CharField(source='status.name', read_only=True)
    contexts = ContextVariableSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectEnvironment
        fields = [
            'id', 'name', 'description', 'type', 'type_name', 'status',
            'status_name', 'available', 'selected', 'contexts', 'created',
            'modified'
        ]


class TalosExecutableSwitchSerializer(serializers.ModelSerializer):

    class Meta:
        model = TalosExecutableSwitch
        fields = '__all__'


class TalosExecutableArgumentSerializer(serializers.ModelSerializer):

    class Meta:
        model = TalosExecutableArgument
        fields = '__all__'


class TalosExecutableArgumentAssignmentSerializer(serializers.ModelSerializer):
    argument_detail = TalosExecutableArgumentSerializer(source='argument',
                                                        read_only=True)

    class Meta:
        model = TalosExecutableArgumentAssignment
        fields = ['id', 'executable', 'order', 'argument', 'argument_detail']


class TalosExecutableSupplementaryFileOrPathSerializer(
        serializers.ModelSerializer):

    class Meta:
        model = TalosExecutableSupplementaryFileOrPath
        fields = '__all__'


class TalosExecutableSerializer(serializers.ModelSerializer):
    switches = TalosExecutableSwitchSerializer(many=True, read_only=True)
    # Using source with method from model
    rendered_executable = serializers.SerializerMethodField()
    argument_assignments = TalosExecutableArgumentAssignmentSerializer(
        source='talosexecutableargumentassignment_set',
        many=True,
        read_only=True)
    files = TalosExecutableSupplementaryFileOrPathSerializer(
        source='talosexecutablesupplementaryfileorpath_set',
        many=True,
        read_only=True)

    class Meta:
        model = TalosExecutable
        fields = [
            'id', 'name', 'description', 'internal', 'working_path',
            'executable', 'log', 'switches', 'rendered_executable',
            'argument_assignments', 'files'
        ]

    def get_rendered_executable(self, obj) -> str:
        """
        Returns the executable path with variables interpolated.
        Uses the default/None environment context. 
        To use a specific environment, context must be passed to serializer.
        """
        env = self.context.get('environment')
        return obj.get_rendered_executable(environment=env)
