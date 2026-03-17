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
    CorpusCallosumRequestSerializer,
    CorpusCallosumResponseDTO,
    CorpusCallosumResponseSerializer,
)

logger = logging.getLogger(__name__)

MSG_REIGNITED = 'Neural pathway re-ignited.'
MSG_GENESIS = 'Corpus Callosum Genesis initiated.'
MSG_FRESH_SPIKE = 'Fresh Spike spawned on standing train.'
MSG_INVALID_STATE = 'Corpus Callosum is currently thinking. Please wait.'


class CorpusCallosumViewSet(viewsets.ViewSet):
    """
    Dedicated ViewSet for the Corpus Callosum UI chat bubble.
    Operates statelessly: POST to send messages and organically traverse the standing train.
    """

    permission_classes = [AllowAny]

    @action(
        detail=False,
        methods=['post'],
    )
    def interact(self, request):
        request_serializer = CorpusCallosumRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        user_message = request_serializer.validated_data.get(
            'message', ''
        ).strip()

        pathway_id = NeuralPathway.CORPUS_CALLOSUM

        # 1. The Bouncer: Find the Standing Train
        standing_train = (
            SpikeTrain.objects.filter(pathway_id=pathway_id)
            .order_by('-created')
            .first()
        )

        if not standing_train:
            # 2A. The Genesis: Create the very first standing train
            pathway = NeuralPathway.objects.get(id=pathway_id)
            standing_train = SpikeTrain.objects.create(
                pathway=pathway,
                environment_id=pathway.environment_id,
                status_id=3,  # RUNNING
            )
            response_msg = MSG_GENESIS
        else:
            response_msg = MSG_FRESH_SPIKE

        # 3. Find the active reasoning session on this train
        session = (
            ReasoningSession.objects.filter(spike__spike_train=standing_train)
            .order_by('-created')
            .first()
        )

        if session:
            if session.status_id == ReasoningStatusID.ATTENTION_REQUIRED:
                # 4A. The Train is Paused. Natively attach memory and wake it up!
                if user_message:
                    last_turn = session.turns.order_by('-turn_number').first()
                    if last_turn:
                        ChatMessage.objects.create(
                            session=session,
                            turn=last_turn,
                            role_id=ChatMessageRole.USER,
                            content=user_message,
                        )

                session.status_id = ReasoningStatusID.ACTIVE
                session.save(update_fields=['status_id'])

                # Kick the Celery worker
                cast_cns_spell.delay(session.spike_id)

                dto = CorpusCallosumResponseDTO(
                    ok=True,
                    message=MSG_REIGNITED,
                    spike_train_id=str(standing_train.id),
                )
                return Response(
                    CorpusCallosumResponseSerializer(instance=dto).data,
                    status=status.HTTP_200_OK,
                )

            elif session.status_id in [
                ReasoningStatusID.ACTIVE,
                ReasoningStatusID.PENDING,
            ]:
                # 4B. Train is currently processing
                return Response(
                    {
                        'ok': False,
                        'message': MSG_INVALID_STATE,
                        'spike_train_id': str(standing_train.id),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 5. The previous conversation naturally concluded (or Genesis).
        # Spawn a fresh Spike and PRE-SEED the ReasoningSession.

        if standing_train.status_id != 3:
            standing_train.status_id = 3
            standing_train.save(update_fields=['status_id'])

        # Grab the root neuron
        root_neuron = Neuron.objects.filter(
            pathway_id=pathway_id, is_root=True
        ).first()
        if not root_neuron:
            return Response(
                {
                    'ok': False,
                    'message': 'Corpus Callosum Root Neuron missing!',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        spike = Spike.objects.create(
            spike_train=standing_train,
            neuron=root_neuron,
            effector_id=root_neuron.effector_id,
            status_id=1,  # CREATED
            blackboard={},
        )

        # CRITICAL: We create the session PRE-PAUSED (ATTENTION_REQUIRED) so that
        # FrontalLobe._initialize_session natively adopts it rather than overwriting it!
        new_session = ReasoningSession.objects.create(
            spike=spike,
            status_id=ReasoningStatusID.ATTENTION_REQUIRED,
            max_turns=50,
            identity_disc_id=IdentityDisc.CORPUS_CALLOSUM,
        )

        first_turn = ReasoningTurn.objects.create(
            session=new_session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )

        if user_message:
            ChatMessage.objects.create(
                session=new_session,
                turn=first_turn,
                role_id=ChatMessageRole.USER,
                content=user_message,
            )

        # Re-ignite! The Frontal Lobe will boot, flip the status to ACTIVE,
        # read the DB history, and organically process your message.
        cast_cns_spell.delay(spike.id)

        dto = CorpusCallosumResponseDTO(
            ok=True, message=response_msg, spike_train_id=str(standing_train.id)
        )
        return Response(
            CorpusCallosumResponseSerializer(instance=dto).data,
            status=status.HTTP_200_OK,
        )
