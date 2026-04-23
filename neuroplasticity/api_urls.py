"""API URL routes for neuroplasticity (Modifier Garden)."""

from rest_framework.routers import DefaultRouter

from .api import NeuralModifierViewSet

V2_NEUROPLASTICITY_ROUTER = DefaultRouter()
V2_NEUROPLASTICITY_ROUTER.register(
    r'neural-modifiers',
    NeuralModifierViewSet,
    basename='neural-modifier',
)
