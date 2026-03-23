from rest_framework import viewsets

from .models import (
    AIMode,
    AIModel,
    AIModelCategory,
    AIModelFamily,
    AIModelPricing,
    AIModelProvider,
    AIModelProviderUsageRecord,
    AIModelRating,
    AIModelSyncLog,
    LLMProvider,
    SyncStatus,
)
from .serializers import (
    AIModeSerializer,
    AIModelCategorySerializer,
    AIModelFamilySerializer,
    AIModelPricingSerializer,
    AIModelProviderSerializer,
    AIModelProviderUsageRecordSerializer,
    AIModelRatingSerializer,
    AIModelSerializer,
    AIModelSyncLogSerializer,
    LLMProviderSerializer,
    SyncStatusSerializer,
)


class LLMProviderViewSet(viewsets.ModelViewSet):
    queryset = LLMProvider.objects.all()
    serializer_class = LLMProviderSerializer


class AIModelCategoryViewSet(viewsets.ModelViewSet):
    queryset = AIModelCategory.objects.all()
    serializer_class = AIModelCategorySerializer


class AIModeViewSet(viewsets.ModelViewSet):
    queryset = AIMode.objects.all()
    serializer_class = AIModeSerializer


class AIModelFamilyViewSet(viewsets.ModelViewSet):
    queryset = AIModelFamily.objects.all()
    serializer_class = AIModelFamilySerializer


class AIModelViewSet(viewsets.ModelViewSet):
    queryset = AIModel.objects.all()
    serializer_class = AIModelSerializer


class AIModelProviderViewSet(viewsets.ModelViewSet):
    queryset = AIModelProvider.objects.all()
    serializer_class = AIModelProviderSerializer


class AIModelPricingViewSet(viewsets.ModelViewSet):
    queryset = AIModelPricing.objects.all()
    serializer_class = AIModelPricingSerializer


class AIModelProviderUsageRecordViewSet(viewsets.ModelViewSet):
    queryset = AIModelProviderUsageRecord.objects.all()
    serializer_class = AIModelProviderUsageRecordSerializer


class SyncStatusViewSet(viewsets.ModelViewSet):
    queryset = SyncStatus.objects.all()
    serializer_class = SyncStatusSerializer


class AIModelSyncLogViewSet(viewsets.ModelViewSet):
    queryset = AIModelSyncLog.objects.all()
    serializer_class = AIModelSyncLogSerializer


class AIModelRatingViewSet(viewsets.ModelViewSet):
    queryset = AIModelRating.objects.all()
    serializer_class = AIModelRatingSerializer
