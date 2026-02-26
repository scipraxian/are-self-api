from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from hydra.models import HydraHeadStatus
from hydra.tasks import cast_hydra_spell

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
            .select_related('status', 'conclusion', 'conclusion__status')
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
                'engrams__source_turns',
            )
            .get(pk=pk)
        )

        serializer = serializers.ReasoningSessionSerializer(session)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def rerun(self, request, pk=None):
        """Reboots the Cortex by restarting the originating HydraHead."""
        session = self.get_object()
        head = session.head

        if not head:
            return Response(
                {'error': 'No associated HydraHead found.'}, status=400
            )

        # 1. Reset the head state
        head.status_id = HydraHeadStatus.PENDING
        head.save(update_fields=['status'])

        # 2. Fire the Celery task to run the AI loop again
        cast_hydra_spell.delay(head.id)

        # 3. Return the Spawn ID so the frontend can redirect to the Monitor
        return Response(
            {
                'status': 'Rebooting',
                'spawn_id': str(head.spawn.id) if head.spawn else None,
            }
        )

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Gracefully signals the Frontal Lobe loop to halt at the next turn."""
        session = self.get_object()
        head = session.head

        if not head:
            return Response(
                {'error': 'No associated HydraHead found.'}, status=400
            )

        head.status_id = HydraHeadStatus.STOPPING
        head.save(update_fields=['status'])

        return Response(
            {
                'status': 'Halt signal sent. The Cortex will spin down after the current turn.'
            }
        )
