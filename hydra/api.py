from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .hydra import Hydra
from .models import HydraHead, HydraSpawn, HydraSpellbook
from .serializers import (
    HydraHeadSerializer,
    HydraNodeTelemetrySerializer,
    HydraSpawnCreateSerializer,
    HydraSpawnSerializer,
    HydraSpellbookSerializer,
)


class HydraSpellbookViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Library of available Protocols (Spellbooks).
    """

    queryset = HydraSpellbook.objects.all().order_by('name')
    serializer_class = HydraSpellbookSerializer
    filterset_fields = ['is_favorite']


class HydraSpawnViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Mission Control.
    MCP Usage:
    - LIST: See recent runs.
    - RETRIEVE: Get status of specific run.
    - CREATE (Launch): Trigger a new build.
    """

    queryset = (
        HydraSpawn.objects.all()
        .select_related('status', 'spellbook', 'environment')
        .order_by('-created')
    )

    def get_serializer_class(self):
        if self.action == 'create':
            return HydraSpawnCreateSerializer
        return HydraSpawnSerializer

    def create(self, request, *args, **kwargs):
        """
        Launch Protocol.
        Accepts: { "spellbook_id": "UUID", "environment_id": "UUID" (optional) }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        book_id = serializer.validated_data['spellbook_id']
        # Note: Environment override logic would go here if we passed it to Hydra init

        try:
            # The Controller Logic
            controller = Hydra(spellbook_id=book_id)
            controller.start()

            # Return the full read serialization of the new spawn
            read_serializer = HydraSpawnSerializer(controller.spawn)
            return Response(
                read_serializer.data, status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {'error': f'Launch Failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['get'])
    def heads(self, request, pk=None):
        """
        Returns a lightweight list of all execution heads for this spawn.
        Useful for finding which specific step failed.
        """
        spawn = self.get_object()
        heads = spawn.heads.all().order_by('created')
        serializer = HydraHeadSerializer(heads, many=True)
        return Response(serializer.data)


class HydraHeadViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Forensics Unit.
    MCP Usage: Retrieve specific Head ID to get full logs/telemetry.
    """

    queryset = HydraHead.objects.all()
    serializer_class = HydraNodeTelemetrySerializer

    def retrieve(self, request, *args, **kwargs):
        """
        Returns rich telemetry including Logs, Command strings, and Exit Codes.
        Warning: Payloads can be large.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
