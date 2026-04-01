from rest_framework import routers

from .api import (
    AIModeViewSet,
    AIModelCategoryViewSet,
    AIModelFamilyViewSet,
    AIModelPricingViewSet,
    AIModelProviderUsageRecordViewSet,
    AIModelProviderViewSet,
    AIModelRatingViewSet,
    AIModelSyncLogViewSet,
    AIModelViewSet,
    LLMProviderViewSet,
    SyncStatusViewSet,
)

V2_HYPOTHALAMUS_ROUTER = routers.SimpleRouter()
V2_HYPOTHALAMUS_ROUTER.register('llm-providers', LLMProviderViewSet)
V2_HYPOTHALAMUS_ROUTER.register('model-categories', AIModelCategoryViewSet)
V2_HYPOTHALAMUS_ROUTER.register('model-modes', AIModeViewSet)
V2_HYPOTHALAMUS_ROUTER.register('model-families', AIModelFamilyViewSet)
V2_HYPOTHALAMUS_ROUTER.register('ai-models', AIModelViewSet)
V2_HYPOTHALAMUS_ROUTER.register('model-providers', AIModelProviderViewSet)
V2_HYPOTHALAMUS_ROUTER.register('model-pricing', AIModelPricingViewSet)
V2_HYPOTHALAMUS_ROUTER.register(
    'usage-records', AIModelProviderUsageRecordViewSet
)
V2_HYPOTHALAMUS_ROUTER.register('sync-status', SyncStatusViewSet)
V2_HYPOTHALAMUS_ROUTER.register('sync-logs', AIModelSyncLogViewSet)
V2_HYPOTHALAMUS_ROUTER.register('model-ratings', AIModelRatingViewSet)
