from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from central_nervous_system.models import SpikeStatus
from central_nervous_system.tasks import cast_cns_spell

from . import serializers
from .models import (
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
    search_fields = ['id', 'conclusion__summary']
    filterset_fields = ['status']

    @action(detail=True, methods=['get'], url_path='graph_data')
    def graph_data(self, request, pk=None):
        """
        Serves the pure, nested JSON tree of the Reasoning Session.
        The frontend JS is responsible for squashing this into D3 neurons and links.
        """
        session = (
            self.get_queryset()
            .select_related('status', 'conclusion', 'conclusion__status')
            .prefetch_related(
                Prefetch(
                    'turns',
                    queryset=ReasoningTurn.objects.select_related(
                        'status'
                    ).order_by('turn_number'),
                ),
                'turns__tool_calls__tool',
                'engrams__source_turns',
            )
            .get(pk=pk)
        )

        serializer = serializers.ReasoningSessionSerializer(session)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def rerun(self, request, pk=None):
        """Reboots the Cortex by restarting the originating Spike."""
        session = self.get_object()
        spike = session.spike

        if not spike:
            return Response(
                {'error': 'No associated Spike found.'}, status=400
            )

        # 1. Reset the spike state
        spike.status_id = SpikeStatus.PENDING
        spike.save(update_fields=['status'])

        # 2. Fire the Celery task to run the AI loop again
        cast_cns_spell.delay(spike.id)

        # 3. Return the SpikeTrain ID so the frontend can redirect to the Monitor
        return Response(
            {
                'status': 'Rebooting',
                'spike_train_id': str(spike.spike_train.id) if spike.spike_train else None,
            }
        )

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Gracefully signals the Frontal Lobe loop to halt at the next turn."""
        session = self.get_object()
        spike = session.spike

        if not spike:
            return Response(
                {'error': 'No associated Spike found.'}, status=400
            )

        spike.status_id = SpikeStatus.STOPPING
        spike.save(update_fields=['status'])

        return Response(
            {
                'status': 'Halt signal sent. The Cortex will spin down after the current turn.'
            }
        )
