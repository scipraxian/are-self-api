from rest_framework import routers

from .api import (
    ParameterEnumViewSet,
    ToolCallViewSet,
    ToolDefinitionViewSet,
    ToolParameterAssignmentViewSet,
    ToolParameterTypeViewSet,
    ToolParameterViewSet,
    ToolUseTypeViewSet,
)

V2_PARIETAL_LOBE = routers.SimpleRouter()
V2_PARIETAL_LOBE.register(
    r'tool-parameter-types',
    ToolParameterTypeViewSet,
    basename='tool-parameter-types',
)
V2_PARIETAL_LOBE.register(
    r'tool-use-types',
    ToolUseTypeViewSet,
    basename='tool-use-types',
)
V2_PARIETAL_LOBE.register(
    r'tool-definitions',
    ToolDefinitionViewSet,
    basename='tool-definitions',
)
V2_PARIETAL_LOBE.register(
    r'tool-parameters',
    ToolParameterViewSet,
    basename='tool-parameters',
)
V2_PARIETAL_LOBE.register(
    r'tool-parameter-assignments',
    ToolParameterAssignmentViewSet,
    basename='tool-parameter-assignments',
)
V2_PARIETAL_LOBE.register(
    r'parameter-enums',
    ParameterEnumViewSet,
    basename='parameter-enums',
)
V2_PARIETAL_LOBE.register(
    r'tool-calls',
    ToolCallViewSet,
    basename='tool-calls',
)
