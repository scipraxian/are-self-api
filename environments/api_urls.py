from rest_framework import routers

from .api import (
    ContextKeyViewSet,
    ContextVariableViewSet,
    EnvironmentStatusViewSet,
    EnvironmentTypeViewSet,
    ProjectEnvironmentViewSet,
    TalosExecutableViewSet,
)

# Define a specific router for this app
ENVIRONMENTS_ROUTER = routers.SimpleRouter()

# Register the ViewSets
ENVIRONMENTS_ROUTER.register(r'environments', ProjectEnvironmentViewSet)
ENVIRONMENTS_ROUTER.register(r'executables', TalosExecutableViewSet)
ENVIRONMENTS_ROUTER.register(r'context-variables', ContextVariableViewSet)
ENVIRONMENTS_ROUTER.register(r'context-keys', ContextKeyViewSet)
ENVIRONMENTS_ROUTER.register(r'environment-types', EnvironmentTypeViewSet)
ENVIRONMENTS_ROUTER.register(r'environment-statuses', EnvironmentStatusViewSet)
