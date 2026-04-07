"""V2 API URL configuration for Peripheral Nervous System."""

from rest_framework import routers

from peripheral_nervous_system.api import (
    NerveTerminalEventViewSet,
    NerveTerminalRegistryViewSet,
    NerveTerminalStatusViewSet,
    NerveTerminalTelemetryViewSet,
)
from peripheral_nervous_system.autonomic_nervous_system import (
    CeleryBeatViewSet,
    CeleryWorkerViewSet,
    SystemControlViewSet,
)

V2_PNS_ROUTER = routers.SimpleRouter()
V2_PNS_ROUTER.register(
    r'beat',
    CeleryBeatViewSet,
    basename='beat',
)

V2_PNS_ROUTER.register(
    r'celery-workers',
    CeleryWorkerViewSet,
    basename='celery-workers',
)

V2_PNS_ROUTER.register(
    r'system-control',
    SystemControlViewSet,
    basename='system-control',
)

V2_PNS_ROUTER.register(
    r'nerve_terminal_statuses',
    NerveTerminalStatusViewSet,
    basename='nerve-terminal-status',
)
V2_PNS_ROUTER.register(
    r'nerve_terminal_registry',
    NerveTerminalRegistryViewSet,
    basename='nerve-terminal-registry',
)
V2_PNS_ROUTER.register(
    r'nerve_terminal_telemetry',
    NerveTerminalTelemetryViewSet,
    basename='nerve-terminal-telemetry',
)
V2_PNS_ROUTER.register(
    r'nerve_terminal_events',
    NerveTerminalEventViewSet,
    basename='nerve-terminal-event',
)
