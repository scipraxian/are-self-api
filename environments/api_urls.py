from rest_framework import routers

from .api import ProjectEnvironmentViewSet, TalosExecutableViewSet

# Define a specific router for this app
ENVIRONMENTS_ROUTER = routers.SimpleRouter()

# Register the ViewSets
ENVIRONMENTS_ROUTER.register(r'environments', ProjectEnvironmentViewSet)
ENVIRONMENTS_ROUTER.register(r'executables', TalosExecutableViewSet)
