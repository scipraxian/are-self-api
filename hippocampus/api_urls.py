from rest_framework import routers

from .api import (
    EngramTagViewSet,
    EngramViewSet,
)

V2_HIPPOCAMPUS_ROUTER = routers.SimpleRouter()
V2_HIPPOCAMPUS_ROUTER.register(
    r'engram_tags', EngramTagViewSet, basename='engram_tags'
)
V2_HIPPOCAMPUS_ROUTER.register(
    r'engrams', EngramViewSet, basename='engrams'
)
