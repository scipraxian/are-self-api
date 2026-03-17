from rest_framework.viewsets import ModelViewSet

from hippocampus.models import TalosEngram, TalosEngramTag
from hippocampus.serializers import (
    TalosEngramSerializer,
    TalosEngramTagSerializer,
)


class TalosEngramTagViewSet(ModelViewSet):
    queryset = TalosEngramTag.objects.all()
    serializer_class = TalosEngramTagSerializer


class TalosEngramViewSet(ModelViewSet):
    queryset = TalosEngram.objects.all()
    serializer_class = TalosEngramSerializer
