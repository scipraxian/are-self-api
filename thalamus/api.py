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
    ChatMessage,
    ChatMessageRole,
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from identity.models import IdentityDisc

from .serializers import (
    ThalamusMessageDTO,
    ThalamusMessageListDTO,
    ThalamusMessageListSerializer,
    ThalamusRequestSerializer,
    ThalamusResponseDTO,
    ThalamusResponseSerializer,
)

logger = logging.getLogger(__name__)


class ThalamusViewSet(viewsets.ViewSet):
    """
    Dedicated ViewSet for the Thalamus UI chat bubble.
    Statelessly routes human chat into the AI's standing ReasoningSession.
    """

    permission_classes = [AllowAny]

    @action(
        detail=False,
        methods=['post'],
    )
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

        if (
            session
            and session.status_id == ReasoningStatusID.ATTENTION_REQUIRED
        ):
            # 3A. RE-IGNITION: The AI was paused waiting for you.
            last_turn = session.turns.order_by('-turn_number').first()

            ChatMessage.objects.create(
                session=session,
                turn=last_turn,
                role_id=ChatMessageRole.USER,
                content=user_message,
            )

            cast_cns_spell.delay(session.spike_id)

            dto = ThalamusResponseDTO(
                ok=True, message='Neural pathway re-ignited.'
            )
            return Response(
                ThalamusResponseSerializer(instance=dto).data,
                status=status.HTTP_200_OK,
            )

        elif session and session.status_id in [
            ReasoningStatusID.ACTIVE,
            ReasoningStatusID.PENDING,
        ]:
            return Response(
                {
                    'ok': False,
                    'message': 'Thalamus is currently thinking.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3B. GENESIS / FRESH START: No active session exists. We build it and pre-seed your message.
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

        # Pre-seed as ATTENTION_REQUIRED so FrontalLobe natively adopts it
        new_session = ReasoningSession.objects.create(
            spike=spike,
            status_id=ReasoningStatusID.ATTENTION_REQUIRED,
            max_turns=50,
            identity_disc_id=IdentityDisc.THALAMUS,
        )

        first_turn = ReasoningTurn.objects.create(
            session=new_session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )

        ChatMessage.objects.create(
            session=new_session,
            turn=first_turn,
            role_id=ChatMessageRole.USER,
            content=user_message,
        )

        cast_cns_spell.delay(spike.id)

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
        Hydrates the assistant-ui chat thread and handles polling.
        Returns the clean 'user' and 'assistant' history of the Standing Train.
        """
        pathway_id = NeuralPathway.THALAMUS
        standing_train = (
            SpikeTrain.objects.filter(pathway_id=pathway_id)
            .order_by('-created')
            .first()
        )

        if not standing_train:
            empty_dto = ThalamusMessageListDTO(messages=[])
            return Response(
                ThalamusMessageListSerializer(instance=empty_dto).data,
                status=status.HTTP_200_OK,
            )

        session = (
            ReasoningSession.objects.filter(spike__spike_train=standing_train)
            .order_by('-created')
            .first()
        )

        if not session:
            empty_dto = ThalamusMessageListDTO(messages=[])
            return Response(
                ThalamusMessageListSerializer(instance=empty_dto).data,
                status=status.HTTP_200_OK,
            )

        # 1. Fetch non-volatile chat messages natively
        # We strictly filter for 'user' and 'assistant' roles to match the assistant-ui schema perfectly.
        chat_msgs = (
            ChatMessage.objects.filter(
                session=session,
                is_volatile=False,
                role__name__in=['user', 'assistant'],
            )
            .select_related('role')
            .order_by('created')
        )

        # 2. Map directly to DTOs
        messages_payload = []
        for msg in chat_msgs:
            if msg.content and msg.content.strip():
                messages_payload.append(
                    ThalamusMessageDTO(
                        role=msg.role.name.lower(), content=msg.content.strip()
                    )
                )

        # 3. Return the strongly typed response
        response_dto = ThalamusMessageListDTO(messages=messages_payload)
        return Response(
            ThalamusMessageListSerializer(instance=response_dto).data,
            status=status.HTTP_200_OK,
        )
