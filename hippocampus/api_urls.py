from rest_framework import routers

from .api import (
    TalosEngramTagViewSet,
    TalosEngramViewSet,
)

V2_HIPPOCAMPUS_ROUTER = routers.SimpleRouter()
V2_HIPPOCAMPUS_ROUTER.register(
    r'engram_tags', TalosEngramTagViewSet, basename='engram_tags'
)
V2_HIPPOCAMPUS_ROUTER.register(
    r'engrams', TalosEngramViewSet, basename='engrams'
)
