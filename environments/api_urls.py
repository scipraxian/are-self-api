from rest_framework import routers

from .api import (
    ContextKeyViewSet,
    ContextVariableViewSet,
    EnvironmentStatusViewSet,
    ExecutableArgumentAssignmentViewSet,
    ExecutableArgumentViewSet,
    ExecutableViewSet,
    ProjectEnvironmentViewSet,
)

# Define a specific router for this app
ENVIRONMENTS_ROUTER = routers.SimpleRouter()

# Register the ViewSets
ENVIRONMENTS_ROUTER.register(r'environments', ProjectEnvironmentViewSet)
ENVIRONMENTS_ROUTER.register(r'executables', ExecutableViewSet)
ENVIRONMENTS_ROUTER.register(r'context-variables', ContextVariableViewSet)
ENVIRONMENTS_ROUTER.register(r'context-keys', ContextKeyViewSet)
ENVIRONMENTS_ROUTER.register(r'environment-statuses', EnvironmentStatusViewSet)
ENVIRONMENTS_ROUTER.register(r'executable-arguments', ExecutableArgumentViewSet)
ENVIRONMENTS_ROUTER.register(
    r'executable-argument-assignments', ExecutableArgumentAssignmentViewSet
)
