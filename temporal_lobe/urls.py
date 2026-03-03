from rest_framework import routers

from temporal_lobe.api import TemporalViewSet

V2_TEMPORAL_LOBE_ROUTER = routers.SimpleRouter()
V2_TEMPORAL_LOBE_ROUTER.register(
    r'temporal_lobe', TemporalViewSet, basename='temporal-lobe'
)
