from rest_framework.viewsets import ModelViewSet

from .models import (
    ParameterEnum,
    ToolCall,
    ToolDefinition,
    ToolParameter,
    ToolParameterAssignment,
    ToolParameterType,
    ToolUseType,
)
from .serializers import (
    ParameterEnumSerializer,
    ToolCallSerializer,
    ToolDefinitionSerializer,
    ToolParameterAssignmentSerializer,
    ToolParameterSerializer,
    ToolParameterTypeSerializer,
    ToolUseTypeSerializer,
)


class ToolParameterTypeViewSet(ModelViewSet):
    queryset = ToolParameterType.objects.all()
    serializer_class = ToolParameterTypeSerializer


class ToolUseTypeViewSet(ModelViewSet):
    queryset = ToolUseType.objects.all()
    serializer_class = ToolUseTypeSerializer


class ToolDefinitionViewSet(ModelViewSet):
    queryset = ToolDefinition.objects.select_related('use_type').all()
    serializer_class = ToolDefinitionSerializer


class ToolParameterViewSet(ModelViewSet):
    queryset = ToolParameter.objects.select_related('type').all()
    serializer_class = ToolParameterSerializer


class ToolParameterAssignmentViewSet(ModelViewSet):
    queryset = ToolParameterAssignment.objects.select_related(
        'tool', 'parameter'
    ).all()
    serializer_class = ToolParameterAssignmentSerializer


class ParameterEnumViewSet(ModelViewSet):
    queryset = ParameterEnum.objects.select_related('parameter').all()
    serializer_class = ParameterEnumSerializer


class ToolCallViewSet(ModelViewSet):
    queryset = ToolCall.objects.select_related('turn', 'tool').all()
    serializer_class = ToolCallSerializer

