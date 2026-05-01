"""API URL routes for neuroplasticity (Modifier Garden)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .api import NeuralModifierViewSet, serve_genome_media

V2_NEUROPLASTICITY_ROUTER = DefaultRouter()
V2_NEUROPLASTICITY_ROUTER.register(
    r'neural-modifiers',
    NeuralModifierViewSet,
    basename='neural-modifier',
)

# Non-router routes that share the /api/v2/ prefix. The core media
# resolver: every bundle's display=FILE Avatar bytes (and any future
# bundle-shipped media) are served here. One route, every bundle uses
# it — bundles do NOT ship their own media routes.
V2_NEUROPLASTICITY_PATHS = [
    path(
        'genomes/<slug:slug>/media/<str:filename>',
        serve_genome_media,
        name='genome-media',
    ),
]
