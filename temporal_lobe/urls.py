from rest_framework import routers

from temporal_lobe.api import (
    IterationDefinitionViewSet,
    IterationViewSet,
    TemporalViewSet,
)

V2_TEMPORAL_LOBE_ROUTER = routers.SimpleRouter()
V2_TEMPORAL_LOBE_ROUTER.register(
    r'temporal_lobe', TemporalViewSet, basename='temporal-lobe'
)
V2_TEMPORAL_LOBE_ROUTER.register(
    r'iterations', IterationViewSet, basename='iterations'
)
V2_TEMPORAL_LOBE_ROUTER.register(
    r'iteration-definitions',
    IterationDefinitionViewSet,
    basename='iteration-definitions',
)
