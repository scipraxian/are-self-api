from asgiref.sync import async_to_sync

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from peripheral_nervous_system.models import (
    NerveTerminalEvent,
    NerveTerminalRegistry,
    NerveTerminalStatus,
    NerveTerminalTelemetry,
)
from peripheral_nervous_system.peripheral_nervous_system import _run_async_scan
from peripheral_nervous_system.serializers import (
    NerveTerminalEventSerializer,
    NerveTerminalRegistrySerializer,
    NerveTerminalStatusSerializer,
    NerveTerminalTelemetrySerializer,
)


class NerveTerminalStatusViewSet(viewsets.ModelViewSet):
    queryset = NerveTerminalStatus.objects.all().order_by('name')
    serializer_class = NerveTerminalStatusSerializer


class NerveTerminalRegistryViewSet(viewsets.ModelViewSet):
    queryset = (
        NerveTerminalRegistry.objects.select_related('status')
        .all()
        .order_by('hostname')
    )
    serializer_class = NerveTerminalRegistrySerializer

    @action(detail=False, methods=['post'])
    def scan(self, request):
        """Trigger a subnet scan to discover and register agents."""
        try:
            registered = async_to_sync(_run_async_scan)(
                subnet_prefix=request.data.get('subnet_prefix', '192.168.1.'),
                port=int(request.data.get('port', 5005)),
            )

            return Response({
                'found': len(registered),
                'registered': registered,
                'message': f'Scan complete. Found {len(registered)} agents.',
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NerveTerminalTelemetryViewSet(viewsets.ModelViewSet):
    queryset = (
        NerveTerminalTelemetry.objects.select_related('target', 'target__status')
        .all()
        .order_by('-timestamp')
    )
    serializer_class = NerveTerminalTelemetrySerializer


class NerveTerminalEventViewSet(viewsets.ModelViewSet):
    queryset = (
        NerveTerminalEvent.objects.select_related('target', 'target__status')
        .all()
        .order_by('-timestamp')
    )
    serializer_class = NerveTerminalEventSerializer

