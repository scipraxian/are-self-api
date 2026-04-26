from rest_framework import routers

from central_nervous_system.api_v2 import (
    AxonViewSetV2,
    CNSDistributionModeViewSetV2,
    EffectorArgumentAssignmentViewSetV2,
    EffectorContextViewSetV2,
    EffectorViewSetV2,
    NeuralPathwayViewSetV2,
    NeuronViewSetV2,
    SpikeTrainViewSetV2,
    SpikeViewSetV2,
)
from central_nervous_system.urls._v2_bundle_discovery import (
    _discover_bundle_routers,
)
from central_nervous_system.views.v2_viewsets import Pathway3DViewSet

V2_CNS_ROUTER = routers.SimpleRouter()
V2_CNS_ROUTER.register(r'pathways-3d', Pathway3DViewSet, basename='pathway-3d')
V2_CNS_ROUTER.register(
    r'spiketrains', SpikeTrainViewSetV2, basename='v2-spiketrain'
)
V2_CNS_ROUTER.register(r'spikes', SpikeViewSetV2, basename='v2-spike')
V2_CNS_ROUTER.register(
    r'neuralpathways', NeuralPathwayViewSetV2, basename='v2-neuralpathway'
)
V2_CNS_ROUTER.register(r'neurons', NeuronViewSetV2, basename='v2-neuron')
V2_CNS_ROUTER.register(r'axons', AxonViewSetV2, basename='v2-axon')
V2_CNS_ROUTER.register(r'effectors', EffectorViewSetV2, basename='v2-effector')
V2_CNS_ROUTER.register(
    r'effector-contexts',
    EffectorContextViewSetV2,
    basename='v2-effector-context',
)
V2_CNS_ROUTER.register(
    r'effector-argument-assignments',
    EffectorArgumentAssignmentViewSetV2,
    basename='v2-effector-arg-assignment',
)
V2_CNS_ROUTER.register(
    r'distribution-modes',
    CNSDistributionModeViewSetV2,
    basename='v2-distribution-mode',
)


_discover_bundle_routers(V2_CNS_ROUTER)
