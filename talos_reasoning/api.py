from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import serializers
from .models import (
    ReasoningGoal,
    ReasoningSession,
    ReasoningTurn,
)


class ReasoningSessionViewSet(viewsets.ModelViewSet):
    """
    Command Center for Talos AGI Reasoning Sessions.
    """

    queryset = ReasoningSession.objects.all().order_by('-created')
    serializer_class = serializers.ReasoningSessionSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    # Fixed to point to the new related model
    search_fields = ['goals__rendered_goal']
    filterset_fields = ['status']

    @action(detail=True, methods=['get'], url_path='graph_data')
    def graph_data(self, request, pk=None):
        """
        Serves the pure, nested JSON tree of the Reasoning Session.
        The frontend JS is responsible for squashing this into D3 nodes and links.
        """
        session = (
            self.get_queryset()
            .select_related('status')
            .prefetch_related(
                Prefetch(
                    'goals',
                    queryset=ReasoningGoal.objects.select_related('status'),
                ),
                Prefetch(
                    'turns',
                    queryset=ReasoningTurn.objects.select_related(
                        'status'
                    ).order_by('turn_number'),
                ),
                'turns__tool_calls__tool',
                'turns__turn_goals',
                'engram__source_turns',
            )
            .get(pk=pk)
        )

        serializer = serializers.ReasoningSessionSerializer(session)
        return Response(serializer.data)
