from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from central_nervous_system.models import SpikeStatus
from central_nervous_system.tasks import fire_spike
from frontal_lobe.models import ReasoningStatusID
from frontal_lobe.serializers import (
    KEY_REPLY,
    ResumeSessionRequestSerializer,
    ResumeSessionResponseDTO,
    ResumeSessionResponseSerializer,
)
from thalamus.serializers import (
    ThalamusMessageListDTO,
    ThalamusMessageListSerializer,
)
from thalamus.thalamus import (
    get_chat_history,
    inject_swarm_chatter,
)

from . import serializers
from .models import ReasoningSession, ReasoningTurn

MSG_REIGNITED = 'Neural pathway re-ignited.'
MSG_INVALID_STATE = (
    'Session is not awaiting attention. Current status: {status_id}'
)


class ReasoningSessionViewSet(viewsets.ModelViewSet):
    """Command Center for Are-Self AGI Reasoning Sessions."""

    queryset = ReasoningSession.objects.all().order_by('-modified')
    serializer_class = serializers.ReasoningSessionLiteSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    search_fields = ['id', 'conclusion__summary']
    filterset_fields = ['status']

    @action(detail=True, methods=['get'], url_path='graph_data')
    def graph_data(self, request, pk=None):
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
        serializer = serializers.ReasoningSessionGraphSerializer(session)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def rerun(self, request, pk=None):
        """Reboots the Cortex by restarting the originating Spike."""
        session = self.get_object()
        spike = session.spike

        if not spike:
            return Response({'error': 'No associated Spike found.'}, status=400)

        spike.status_id = SpikeStatus.PENDING
        spike.save(update_fields=['status'])
        fire_spike.delay(spike.id)

        return Response(
            {
                'status': 'Rebooting',
                'spike_train_id': str(spike.spike_train.id)
                if spike.spike_train
                else None,
            }
        )

    @action(detail=True, methods=['post'])
    def attention_required(self, request, pk=None):
        """The graceful pause trigger."""
        session = self.get_object()
        session.status_id = ReasoningStatusID.ATTENTION_REQUIRED

        # NOTE: saving this triggers the broadcast_session_status signal in Thalamus!
        session.save(update_fields=['status_id'])

        return Response({'status': 'Attention required'})

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """The flat chat pipeline for assistant-ui."""
        session = self.get_object()
        include_volatile = (
            request.query_params.get('volatile', 'false').lower() == 'true'
        )

        messages_payload = get_chat_history(
            session, include_volatile=include_volatile
        )
        response_dto = ThalamusMessageListDTO(messages=messages_payload)

        return Response(
            ThalamusMessageListSerializer(instance=response_dto).data
        )

    @action(
        detail=True,
        methods=['post'],
        serializer_class=ResumeSessionRequestSerializer,
    )
    def resume(self, request, pk=None):
        """Injects human chatter into a ReasoningSession and ensures it is awake."""
        session = self.get_object()

        request_serializer = self.get_serializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        user_reply = request_serializer.validated_data.get(KEY_REPLY, '')

        # Drop into the async queue!
        inject_swarm_chatter(session, role='user', text=user_reply)

        success_dto = ResumeSessionResponseDTO(
            ok=True, message='Swarm chatter injected. Neural pathway active.'
        )
        return Response(
            ResumeSessionResponseSerializer(instance=success_dto).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Gracefully signals the Frontal Lobe loop to halt at the next turn."""
        session = self.get_object()
        spike = session.spike
        if not spike:
            return Response({'error': 'No associated Spike found.'}, status=400)

        spike.status_id = SpikeStatus.STOPPING
        spike.save(update_fields=['status'])
        return Response(
            {
                'status': 'Halt signal sent. The Cortex will spin down after the current turn.'
            }
        )


class ReasoningTurnViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Deep inspection endpoint for individual cognitive cycles.
    Used by the frontend graph to view the raw Ledger (request/response payloads, tokens, costs).
    """

    queryset = (
        ReasoningTurn.objects.select_related(
            'status',
            'session',
            'model_usage_record',
            'model_usage_record__ai_model',
            'model_usage_record__ai_model_provider',
        )
        .prefetch_related('tool_calls__tool')
        .order_by('-created')
    )

    # Using the serializer you defined earlier!
    serializer_class = serializers.ReasoningTurnSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['session', 'status']
