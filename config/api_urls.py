"""System-wide URL routing (Config)."""

from django.urls import path

from config.api import (
    LatestSessionsAPIView,
    LatestSpikesAPIView,
    StatsAPIView,
)

CONFIG_URLS = [
    path('stats/', StatsAPIView.as_view(), name='stats'),
    path('latest-spikes/', LatestSpikesAPIView.as_view(), name='latest-spikes'),
    path(
        'latest-sessions/',
        LatestSessionsAPIView.as_view(),
        name='latest-sessions',
    ),
]
