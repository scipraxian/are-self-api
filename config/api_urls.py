"""System-wide URL routing (Config)."""

from django.urls import path

from config.api import StatsAPIView

CONFIG_URLS = [
    path('stats/', StatsAPIView.as_view(), name='stats'),
]
