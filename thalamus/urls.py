from rest_framework import routers

from thalamus.api import ThalamusViewSet

V2_THALAMUS = routers.SimpleRouter()
V2_THALAMUS.register(
    r'thalamus', ThalamusViewSet, basename='thalamus'
)
