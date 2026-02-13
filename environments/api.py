from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ProjectEnvironment, TalosExecutable
from .serializers import ProjectEnvironmentSerializer, TalosExecutableSerializer


class ProjectEnvironmentViewSet(viewsets.ModelViewSet):
    """
    Manages Project Contexts.
    MCP Usage: List to find environments, POST to 'select' to switch active context.
    """
    queryset = ProjectEnvironment.objects.all().order_by('name')
    serializer_class = ProjectEnvironmentSerializer

    @action(detail=True, methods=['post'])
    def select(self, request, pk=None):
        """
        Sets this environment as the active global context for all Talos operations.
        """
        env = self.get_object()
        if not env.available:
            return Response(
                {'error': f'Environment {env.name} is marked unavailable.'},
                status=status.HTTP_409_CONFLICT
            )

        # Atomic switch logic matches models.py save() behavior but explicit here for API clarity
        with transaction.atomic():
            ProjectEnvironment.objects.filter(selected=True).exclude(id=env.id).update(selected=False)
            env.selected = True
            env.save()

        return Response({'status': f'Active Environment set to: {env.name}'})


class TalosExecutableViewSet(viewsets.ModelViewSet):
    """
    Registry of Tools/Executables.
    MCP Usage: Read-only lookup to understand available tools and their default flags.
    """
    queryset = TalosExecutable.objects.all().order_by('name')
    serializer_class = TalosExecutableSerializer
    # Executable updates are rare/dangerous; restricting to admin or explicit PATCH
    http_method_names = ['get', 'head', 'options', 'patch']