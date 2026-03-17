# frontal_lobe/api_urls.py

from rest_framework import routers

from .api import ModelRegistryViewSet, ReasoningSessionViewSet

V2_REASONING_ROUTER = routers.SimpleRouter()
V2_REASONING_ROUTER.register(
    r'reasoning_sessions', ReasoningSessionViewSet, basename='reasoningsession'
)
V2_REASONING_ROUTER.register(
    r'model_registry', ModelRegistryViewSet, basename='modelregistry'
)
