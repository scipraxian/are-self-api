from rest_framework import routers

from central_nervous_system.api import (
    CNSNeuralPathwayConnectionWireViewSet,
    CNSNeuralPathwayNodeViewSet,
    CNSNeuralPathwayViewSet,
    EffectorBookNodeContextViewSet,
    EffectorViewSet,
    SpikeTrainViewSet,
    SpikeViewSet,
)

CNS_ROUTER = routers.SimpleRouter()

CNS_ROUTER.register(r'spike_trains', SpikeTrainViewSet, basename='cns_spawn')
CNS_ROUTER.register(
    r'pathways', CNSNeuralPathwayViewSet, basename='cns_spellbook'
)
CNS_ROUTER.register(r'spikes', SpikeViewSet, basename='cns_head')
CNS_ROUTER.register(r'effectors', EffectorViewSet, basename='cns_spell')
CNS_ROUTER.register(
    r'neurons', CNSNeuralPathwayNodeViewSet, basename='cns_spellbook_node'
)
CNS_ROUTER.register(
    r'axons',
    CNSNeuralPathwayConnectionWireViewSet,
    basename='cns_spellbook_connection_wire',
)
CNS_ROUTER.register(
    r'node-contexts',
    EffectorBookNodeContextViewSet,
    basename='cns_spellbook_node_context',
)
