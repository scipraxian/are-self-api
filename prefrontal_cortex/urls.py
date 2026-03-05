from rest_framework import routers

from prefrontal_cortex.api import (
    PFCCommentViewSet,
    PFCEpicViewSet,
    PFCItemStatusViewSet,
    PFCStoryViewSet,
    PFCTagViewSet,
    PFCTaskViewSet,
)

V2_PREFRONTAL_CORTEX_ROUTER = routers.SimpleRouter()
V2_PREFRONTAL_CORTEX_ROUTER.register(
    r'pre-frontal-item-status',
    PFCItemStatusViewSet,
    basename='pre-frontal-item-status',
)
V2_PREFRONTAL_CORTEX_ROUTER.register(
    r'pfc-tags', PFCTagViewSet, basename='pfc-tag'
)
V2_PREFRONTAL_CORTEX_ROUTER.register(
    r'pfc-epics', PFCEpicViewSet, basename='pfc-epic'
)
V2_PREFRONTAL_CORTEX_ROUTER.register(
    r'pfc-stories', PFCStoryViewSet, basename='pfc-story'
)
V2_PREFRONTAL_CORTEX_ROUTER.register(
    r'pfc-tasks', PFCTaskViewSet, basename='pfc-task'
)
V2_PREFRONTAL_CORTEX_ROUTER.register(
    r'pfc-comments', PFCCommentViewSet, basename='pfc-comment'
)
