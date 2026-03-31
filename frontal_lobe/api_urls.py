from rest_framework import routers

from .api import ReasoningSessionViewSet, ReasoningTurnViewSet

V2_REASONING_ROUTER = routers.SimpleRouter()
V2_REASONING_ROUTER.register(
    r'reasoning_sessions', ReasoningSessionViewSet, basename='reasoningsession'
)
V2_REASONING_ROUTER.register(
    r'reasoning_turns', ReasoningTurnViewSet, basename='reasoningturns'
)
