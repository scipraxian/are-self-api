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

HYDRA_ROUTER = routers.SimpleRouter()

HYDRA_ROUTER.register(r'spawns', CNSSpawnViewSet, basename='hydra_spawn')
HYDRA_ROUTER.register(
    r'spellbooks', CNSSpellbookViewSet, basename='hydra_spellbook'
)
HYDRA_ROUTER.register(r'heads', CNSHeadViewSet, basename='hydra_head')
HYDRA_ROUTER.register(r'spells', CNSSpellViewSet, basename='hydra_spell')
HYDRA_ROUTER.register(
    r'nodes', CNSSpellbookNodeViewSet, basename='hydra_spellbook_node'
)
HYDRA_ROUTER.register(
    r'wires',
    CNSSpellbookConnectionWireViewSet,
    basename='hydra_spellbook_connection_wire',
)
HYDRA_ROUTER.register(
    r'node-contexts',
    CNSSpellBookNodeContextViewSet,
    basename='hydra_spellbook_node_context',
)
