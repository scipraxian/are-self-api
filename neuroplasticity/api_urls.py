"""API URL routes for neuroplasticity (Modifier Garden)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .api import NeuralModifierViewSet, fixture_scan_view

V2_NEUROPLASTICITY_ROUTER = DefaultRouter()
V2_NEUROPLASTICITY_ROUTER.register(
    r'neural-modifiers',
    NeuralModifierViewSet,
    basename='neural-modifier',
)

# Non-viewset routes live here; the config URL layer folds these into
# the v2 namespace alongside the router. The fixture-scan endpoint is
# deliberately outside /neural-modifiers/ because it is about the core
# fixture tree, not about any specific bundle.
NEUROPLASTICITY_V2_URLS = [
    path(
        'genome/fixture-scan/',
        fixture_scan_view,
        name='genome-fixture-scan',
    ),
]
