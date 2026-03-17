from rest_framework import viewsets

from peripheral_nervous_system.models import (
    NerveTerminalEvent,
    NerveTerminalRegistry,
    NerveTerminalStatus,
    NerveTerminalTelemetry,
)
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

