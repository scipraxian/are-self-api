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

HYDRA_ROUTER.register(r'spawns', HydraSpawnViewSet)
HYDRA_ROUTER.register(r'spellbooks', HydraSpellbookViewSet)
HYDRA_ROUTER.register(r'heads', HydraHeadViewSet)
HYDRA_ROUTER.register(r'spells', HydraSpellViewSet)
HYDRA_ROUTER.register(r'nodes', HydraSpellbookNodeViewSet)
HYDRA_ROUTER.register(r'wires', HydraSpellbookConnectionWireViewSet)
HYDRA_ROUTER.register(r'node-contexts', HydraSpellBookNodeContextViewSet)