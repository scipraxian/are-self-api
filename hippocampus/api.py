from rest_framework.viewsets import ModelViewSet

from hippocampus.models import Engram, EngramTag
from hippocampus.serializers import (
    EngramSerializer,
    EngramTagSerializer,
)


class EngramTagViewSet(ModelViewSet):
    queryset = EngramTag.objects.all()
    serializer_class = EngramTagSerializer


class EngramViewSet(ModelViewSet):
    queryset = Engram.objects.all()
    serializer_class = EngramSerializer
