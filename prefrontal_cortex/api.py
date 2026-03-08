from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    PFCComment,
    PFCEpic,
    PFCItemStatus,
    PFCStory,
    PFCTag,
    PFCTask,
)
from .serializers import (
    PFCCommentDetailSerializer,
    PFCCommentSerializer,
    PFCEpicDetailSerializer,
    PFCEpicSerializer,
    PFCItemStatusSerializer,
    PFCStoryDetailSerializer,
    PFCStorySerializer,
    PFCTagSerializer,
    PFCTaskDetailSerializer,
    PFCTaskSerializer,
)


class FullPullMixin:
    """
    Provides a dynamic serializer switch:
    - standard serializer for lists and writes
    - detail_serializer_class for retrieves
    - detail_serializer_class for queries with `?full=true`
    - custom `@action(detail=False, methods=['get'])` for explicit /full/ endpoint
    """

    def get_serializer_class(self):
        if hasattr(self, 'detail_serializer_class'):
            if self.action in ['retrieve', 'full']:
                return self.detail_serializer_class

            if hasattr(self, 'request') and self.request is not None:
                full_param = self.request.query_params.get('full',
                                                           'false').lower()
                if full_param in ['true', '1', 'yes']:
                    return self.detail_serializer_class

        return super().get_serializer_class()

    @action(detail=False, methods=['get'])
    def full(self, request):
        """
        An explicit endpoint to get a full pull instead of using the query param.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class PFCItemStatusViewSet(viewsets.ModelViewSet):
    queryset = PFCItemStatus.objects.all()
    serializer_class = PFCItemStatusSerializer


class PFCTagViewSet(viewsets.ModelViewSet):
    queryset = PFCTag.objects.all()
    serializer_class = PFCTagSerializer


class PFCEpicViewSet(FullPullMixin, viewsets.ModelViewSet):
    queryset = PFCEpic.objects.all()
    serializer_class = PFCEpicSerializer
    detail_serializer_class = PFCEpicDetailSerializer


class PFCStoryViewSet(FullPullMixin, viewsets.ModelViewSet):
    queryset = PFCStory.objects.all()
    serializer_class = PFCStorySerializer
    detail_serializer_class = PFCStoryDetailSerializer


class PFCTaskViewSet(FullPullMixin, viewsets.ModelViewSet):
    queryset = PFCTask.objects.all()
    serializer_class = PFCTaskSerializer
    detail_serializer_class = PFCTaskDetailSerializer


class PFCCommentViewSet(FullPullMixin, viewsets.ModelViewSet):
    queryset = PFCComment.objects.all()
    serializer_class = PFCCommentSerializer
    detail_serializer_class = PFCCommentDetailSerializer
