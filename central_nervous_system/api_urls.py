from rest_framework import routers

from .api import (
    HydraHeadViewSet,
    HydraSpawnViewSet,
    HydraSpellbookConnectionWireViewSet,
    HydraSpellBookNodeContextViewSet,
    HydraSpellbookNodeViewSet,
    HydraSpellbookViewSet,
    HydraSpellViewSet,
)

HYDRA_ROUTER = routers.SimpleRouter()

HYDRA_ROUTER.register(r'spawns', HydraSpawnViewSet, basename='hydra_spawn')
HYDRA_ROUTER.register(
    r'spellbooks', HydraSpellbookViewSet, basename='hydra_spellbook'
)
HYDRA_ROUTER.register(r'heads', HydraHeadViewSet, basename='hydra_head')
HYDRA_ROUTER.register(r'spells', HydraSpellViewSet, basename='hydra_spell')
HYDRA_ROUTER.register(
    r'nodes', HydraSpellbookNodeViewSet, basename='hydra_spellbook_node'
)
HYDRA_ROUTER.register(
    r'wires',
    HydraSpellbookConnectionWireViewSet,
    basename='hydra_spellbook_connection_wire',
)
HYDRA_ROUTER.register(
    r'node-contexts',
    HydraSpellBookNodeContextViewSet,
    basename='hydra_spellbook_node_context',
)
