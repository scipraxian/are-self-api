from rest_framework import routers

from .api import (
    AIModelCapabilitiesViewSet,
    AIModelCategoryViewSet,
    AIModelDescriptionViewSet,
    AIModelFamilyViewSet,
    AIModelPricingViewSet,
    AIModelProviderUsageRecordViewSet,
    AIModelProviderViewSet,
    AIModelRatingViewSet,
    AIModelRolesViewSet,
    AIModelSelectionFilterViewSet,
    AIModelSyncLogViewSet,
    AIModelSyncReportViewSet,
    AIModelTagsViewSet,
    AIModelViewSet,
    AIModeViewSet,
    FailoverStrategyViewSet,
    FailoverTypeViewSet,
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
V2_HYPOTHALAMUS_ROUTER.register('sync-reports', AIModelSyncReportViewSet)
V2_HYPOTHALAMUS_ROUTER.register('model-ratings', AIModelRatingViewSet)
V2_HYPOTHALAMUS_ROUTER.register('failover-types', FailoverTypeViewSet)
V2_HYPOTHALAMUS_ROUTER.register('failover-strategies', FailoverStrategyViewSet)
V2_HYPOTHALAMUS_ROUTER.register(
    'selection-filters', AIModelSelectionFilterViewSet
)
V2_HYPOTHALAMUS_ROUTER.register('model-descriptions', AIModelDescriptionViewSet)
V2_HYPOTHALAMUS_ROUTER.register('model-tags', AIModelTagsViewSet)
V2_HYPOTHALAMUS_ROUTER.register(
    'model-capabilities', AIModelCapabilitiesViewSet
)
V2_HYPOTHALAMUS_ROUTER.register('model-roles', AIModelRolesViewSet)
