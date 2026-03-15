"""V2 API URL configuration for Peripheral Nervous System (autonomic: Celery Beat control)."""

from rest_framework import routers

from peripheral_nervous_system.autonomic_nervous_system import CeleryBeatViewSet

V2_AUTONOMIC_ROUTER = routers.SimpleRouter()
V2_AUTONOMIC_ROUTER.register(
    r'beat',
    CeleryBeatViewSet,
    basename='beat',
)
