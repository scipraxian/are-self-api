from rest_framework import routers

from .api import HydraHeadViewSet, HydraSpawnViewSet, HydraSpellbookViewSet

HYDRA_ROUTER = routers.SimpleRouter()

HYDRA_ROUTER.register(r'spawns', HydraSpawnViewSet)
HYDRA_ROUTER.register(r'spellbooks', HydraSpellbookViewSet)
HYDRA_ROUTER.register(r'heads', HydraHeadViewSet)
