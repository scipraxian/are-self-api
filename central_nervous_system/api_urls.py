from rest_framework import routers

from .api import (
    CNSHeadViewSet,
    CNSSpawnViewSet,
    CNSSpellbookConnectionWireViewSet,
    CNSSpellBookNodeContextViewSet,
    CNSSpellbookNodeViewSet,
    CNSSpellbookViewSet,
    CNSSpellViewSet,
)

CNS_ROUTER = routers.SimpleRouter()

CNS_ROUTER.register(r'spawns', CNSSpawnViewSet, basename='cns_spawn')
CNS_ROUTER.register(
    r'spellbooks', CNSSpellbookViewSet, basename='cns_spellbook'
)
CNS_ROUTER.register(r'heads', CNSHeadViewSet, basename='cns_head')
CNS_ROUTER.register(r'spells', CNSSpellViewSet, basename='cns_spell')
CNS_ROUTER.register(
    r'nodes', CNSSpellbookNodeViewSet, basename='cns_spellbook_node'
)
CNS_ROUTER.register(
    r'wires',
    CNSSpellbookConnectionWireViewSet,
    basename='cns_spellbook_connection_wire',
)
CNS_ROUTER.register(
    r'node-contexts',
    CNSSpellBookNodeContextViewSet,
    basename='cns_spellbook_node_context',
)
