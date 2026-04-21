from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.viewsets import ModelViewSet

from hippocampus.models import Engram, EngramTag

if TYPE_CHECKING:
    from django.db.models import QuerySet
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

    def get_queryset(self) -> 'QuerySet[Engram]':
        queryset = super().get_queryset()
        identity_discs = self.request.query_params.get('identity_discs')
        if identity_discs:
            queryset = queryset.filter(
                identity_discs=identity_discs
            ).distinct()
        sessions = self.request.query_params.get('sessions')
        if sessions:
            queryset = queryset.filter(sessions=sessions).distinct()
        return queryset
