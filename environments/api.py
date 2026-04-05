from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    ContextVariable,
    Executable,
    ExecutableArgument,
    ExecutableArgumentAssignment,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
)
from .serializers import (
    ContextVariableSerializer,
    ExecutableArgumentAssignmentSerializer,
    ExecutableArgumentSerializer,
    ExecutableSerializer,
    ProjectEnvironmentContextKeySerializer,
    ProjectEnvironmentSerializer,
    ProjectEnvironmentStatusSerializer,
    ProjectEnvironmentTypeSerializer,
)


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
        Sets this environment as the active global context for all Are-Self operations.
        """
        env = self.get_object()
        if not env.available:
            return Response(
                {'error': f'Environment {env.name} is marked unavailable.'},
                status=status.HTTP_409_CONFLICT,
            )

        # Atomic switch logic matches models.py save() behavior but explicit here for API clarity
        with transaction.atomic():
            ProjectEnvironment.objects.filter(selected=True).exclude(
                id=env.id
            ).update(selected=False)
            env.selected = True
            env.save()

        return Response({'status': f'Active Environment set to: {env.name}'})


class ExecutableViewSet(viewsets.ModelViewSet):
    """
    Registry of Tools/Executables — full CRUD for the Effector Editor.
    """

    queryset = (
        Executable.objects.all()
        .prefetch_related(
            'switches',
            'executableargumentassignment_set',
            'executableargumentassignment_set__argument',
            'executablesupplementaryfileorpath_set',
        )
        .order_by('name')
    )
    serializer_class = ExecutableSerializer


class ContextVariableViewSet(viewsets.ModelViewSet):
    queryset = ContextVariable.objects.all().select_related('key')
    serializer_class = ContextVariableSerializer
    filterset_fields = ['environment']


class ContextKeyViewSet(viewsets.ModelViewSet):
    queryset = ProjectEnvironmentContextKey.objects.all().order_by('name')
    serializer_class = ProjectEnvironmentContextKeySerializer


class EnvironmentTypeViewSet(viewsets.ModelViewSet):
    queryset = ProjectEnvironmentType.objects.all()
    serializer_class = ProjectEnvironmentTypeSerializer


class EnvironmentStatusViewSet(viewsets.ModelViewSet):
    queryset = ProjectEnvironmentStatus.objects.all()
    serializer_class = ProjectEnvironmentStatusSerializer


class ExecutableArgumentViewSet(viewsets.ModelViewSet):
    """
    CRUD for standalone argument definitions.
    These are the reusable argument templates that get assigned to Executables/Effectors.
    """

    queryset = ExecutableArgument.objects.all().order_by('name')
    serializer_class = ExecutableArgumentSerializer


class ExecutableArgumentAssignmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for the join table linking arguments to executables (with order).
    Filterable by executable FK.
    """

    queryset = (
        ExecutableArgumentAssignment.objects.all()
        .select_related('argument')
        .order_by('order')
    )
    serializer_class = ExecutableArgumentAssignmentSerializer
    filterset_fields = ['executable']
