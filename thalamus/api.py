import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from central_nervous_system.models import (
    NeuralPathway,
    Neuron,
    Spike,
    SpikeTrain,
    SpikeTrainStatus,
)
from central_nervous_system.tasks import cast_cns_spell
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from identity.models import IdentityDisc

from .serializers import (
    ThalamusMessageListDTO,
    ThalamusMessageListSerializer,
    ThalamusRequestSerializer,
    ThalamusResponseDTO,
    ThalamusResponseSerializer,
)
from .thalamus import get_chat_history, inject_human_reply

logger = logging.getLogger(__name__)


class ThalamusViewSet(viewsets.ViewSet):
    """
    Dedicated ViewSet for the Thalamus UI chat bubble.
    Statelessly routes human chat into the AI's standing ReasoningSession.
    """

    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def interact(self, request):
        serializer = ThalamusRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_message = serializer.validated_data['message'].strip()

        pathway_id = NeuralPathway.THALAMUS
        standing_train = (
            SpikeTrain.objects.filter(pathway_id=pathway_id)
            .order_by('-created')
            .first()
        )

        # 1. Ensure the Standing Train exists and is RUNNING
        if not standing_train:
            pathway = NeuralPathway.objects.get(id=pathway_id)
            standing_train = SpikeTrain.objects.create(
                pathway=pathway,
                environment_id=pathway.environment_id,
                status_id=SpikeTrainStatus.RUNNING,
            )
        elif standing_train.status_id != SpikeTrainStatus.RUNNING:
            standing_train.status_id = SpikeTrainStatus.RUNNING
            standing_train.save(update_fields=['status_id'])

        # 2. Find the active reasoning session on this train
        session = (
            ReasoningSession.objects.filter(spike__spike_train=standing_train)
            .order_by('-created')
            .first()
        )

        # 3A. RE-IGNITION: The AI was paused waiting for you.
        if (
            session
            and session.status_id == ReasoningStatusID.ATTENTION_REQUIRED
        ):
            # Hand off to the DRY operation
            inject_human_reply(session, user_message)

            dto = ThalamusResponseDTO(
                ok=True, message='Neural pathway re-ignited.'
            )
            return Response(
                ThalamusResponseSerializer(instance=dto).data,
                status=status.HTTP_200_OK,
            )

        # 3B. BUSY STATE
        elif session and session.status_id in [
            ReasoningStatusID.ACTIVE,
            ReasoningStatusID.PENDING,
        ]:
            # Now properly using your DTOs instead of raw dicts!
            dto = ThalamusResponseDTO(
                ok=False, message='Thalamus is currently thinking.'
            )
            return Response(
                ThalamusResponseSerializer(instance=dto).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3C. GENESIS / FRESH START
        cc_neuron = Neuron.objects.filter(
            pathway_id=pathway_id, is_root=False
        ).first()
        spike = Spike.objects.create(
            spike_train=standing_train,
            neuron=cc_neuron,
            effector_id=cc_neuron.effector_id,
            status_id=1,
            blackboard={},
        )

        new_session = ReasoningSession.objects.create(
            spike=spike,
            status_id=ReasoningStatusID.ATTENTION_REQUIRED,
            max_turns=50,
            identity_disc_id=IdentityDisc.THALAMUS,
        )

        ReasoningTurn.objects.create(
            session=new_session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )

        # Pre-seed your message using the exact same injection logic
        inject_human_reply(new_session, user_message)

        dto = ThalamusResponseDTO(
            ok=True, message='Fresh Spike spawned with user prompt.'
        )
        return Response(
            ThalamusResponseSerializer(instance=dto).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'])
    def messages(self, request):
        """
        Hydrates the assistant-ui chat thread.
        Returns the clean 'user' and 'assistant' history of the Standing Train.
        """
        pathway_id = NeuralPathway.THALAMUS
        standing_train = (
            SpikeTrain.objects.filter(pathway_id=pathway_id)
            .order_by('-created')
            .first()
        )

        if not standing_train:
            return Response(
                ThalamusMessageListSerializer(
                    instance=ThalamusMessageListDTO(messages=[])
                ).data,
                status=status.HTTP_200_OK,
            )

        session = (
            ReasoningSession.objects.filter(spike__spike_train=standing_train)
            .order_by('-created')
            .first()
        )

        if not session:
            return Response(
                ThalamusMessageListSerializer(
                    instance=ThalamusMessageListDTO(messages=[])
                ).data,
                status=status.HTTP_200_OK,
            )

        # Hand off to the DRY operation
        messages_payload = get_chat_history(session, include_volatile=False)

        response_dto = ThalamusMessageListDTO(messages=messages_payload)
        return Response(
            ThalamusMessageListSerializer(instance=response_dto).data,
            status=status.HTTP_200_OK,
        )
