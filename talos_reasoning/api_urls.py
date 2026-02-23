# talos_reasoning/api_urls.py

from rest_framework import routers

from .api import ReasoningSessionViewSet

REASONING_ROUTER = routers.SimpleRouter()
REASONING_ROUTER.register(
    r'reasoning_sessions', ReasoningSessionViewSet, basename='reasoningsession'
)
