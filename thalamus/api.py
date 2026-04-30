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
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from identity.models import IdentityDisc

from .serializers import (
    ThalamusMessageListDTO,
    ThalamusMessageListSerializer,
    ThalamusModelInfoDTO,
    ThalamusModelInfoSerializer,
    ThalamusRequestSerializer,
    ThalamusResponseDTO,
    ThalamusResponseSerializer,
)
from .thalamus import get_chat_history, inject_swarm_chatter

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

        # 3A. INJECT INTO EXISTING SESSION (Regardless of state)
        if session and session.status_id in [
            ReasoningStatusID.ACTIVE,
            ReasoningStatusID.PENDING,
            ReasoningStatusID.ATTENTION_REQUIRED,
        ]:
            inject_swarm_chatter(session, role='user', text=user_message)
            dto = ThalamusResponseDTO(
                ok=True, message='Swarm chatter injected into standing session.'
            )
            return Response(
                ThalamusResponseSerializer(instance=dto).data,
                status=status.HTTP_200_OK,
            )

        # 3B. GENESIS / FRESH START
        cc_neuron = Neuron.objects.filter(
            pathway_id=pathway_id, is_root=False
        ).first()

        spike = Spike.objects.create(
            spike_train=standing_train,
            neuron=cc_neuron,
            effector_id=cc_neuron.effector_id,
            status_id=1,
            axoplasm={},
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

        # Pre-seed your message into the fresh queue
        inject_swarm_chatter(new_session, role='user', text=user_message)

        dto = ThalamusResponseDTO(
            ok=True, message='Fresh Spike spawned with user prompt.'
        )
        return Response(
            ThalamusResponseSerializer(instance=dto).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'], url_path='model-info')
    def model_info(self, request):
        """Return the Thalamus identity's configured model + live token pressure.

        ``model_name`` and ``context_window`` are a cheap lookup off
        ``IdentityDisc.THALAMUS.selection_filter.preferred_model.ai_model``
        -- configured intent, NOT live routing.  ``current_tokens``
        is the most recent ``ReasoningTurn.model_usage_record.input_tokens``
        on the standing Thalamus session (excluding STOPPED sessions
        the same way ``/messages/`` does, so a freshly-cleared chat
        reports null until the next turn runs).  Any unresolved link
        in either chain collapses to null.  UI refetches on every
        ``ReasoningTurnDigest`` ``activity='saved'`` push.
        """
        try:
            disc = IdentityDisc.objects.select_related(
                'selection_filter__preferred_model__ai_model'
            ).get(id=IdentityDisc.THALAMUS)
            selection_filter = disc.selection_filter
            provider = (
                selection_filter.preferred_model
                if selection_filter else None
            )
            model = provider.ai_model if provider else None
            model_name = model.name if model else None
            context_window = model.context_length if model else None
        except IdentityDisc.DoesNotExist:
            model_name = None
            context_window = None

        current_tokens = self._resolve_current_input_tokens()

        dto = ThalamusModelInfoDTO(
            model_name=model_name,
            context_window=context_window,
            current_tokens=current_tokens,
        )
        return Response(
            ThalamusModelInfoSerializer(instance=dto).data,
            status=status.HTTP_200_OK,
        )

    def _resolve_current_input_tokens(self):
        """Most recent ``input_tokens`` on the standing Thalamus session.

        Walks the same standing-train chain as ``/interact/`` and
        ``/messages/``: latest SpikeTrain on the THALAMUS pathway,
        latest non-STOPPED ReasoningSession on it, highest-numbered
        ReasoningTurn whose ``model_usage_record`` is populated.
        Any null link returns ``None``.
        """
        standing_train = (
            SpikeTrain.objects
            .filter(pathway_id=NeuralPathway.THALAMUS)
            .order_by('-created')
            .first()
        )
        if not standing_train:
            return None
        session = (
            ReasoningSession.objects
            .filter(spike__spike_train=standing_train)
            .exclude(status_id=ReasoningStatusID.STOPPED)
            .order_by('-created')
            .first()
        )
        if not session:
            return None
        recent_turn = (
            session.turns
            .filter(model_usage_record__isnull=False)
            .order_by('-turn_number')
            .select_related('model_usage_record')
            .first()
        )
        if not recent_turn:
            return None
        return recent_turn.model_usage_record.input_tokens

    @action(detail=False, methods=['post'], url_path='clear')
    def clear(self, request):
        """Mark the current Thalamus session as STOPPED.

        After clear() returns, the next ``/interact/`` call falls
        through to the GENESIS / FRESH START path instead of injecting
        into the existing session. Idempotent: clearing twice or
        clearing when nothing is active both return 200 with an
        explanatory message.
        """
        pathway_id = NeuralPathway.THALAMUS
        standing_train = (
            SpikeTrain.objects.filter(pathway_id=pathway_id)
            .order_by('-created')
            .first()
        )
        if not standing_train:
            dto = ThalamusResponseDTO(
                ok=True, message='No standing train; nothing to clear.'
            )
            return Response(
                ThalamusResponseSerializer(instance=dto).data,
                status=status.HTTP_200_OK,
            )

        session = (
            ReasoningSession.objects.filter(spike__spike_train=standing_train)
            .order_by('-created')
            .first()
        )
        terminal_states = (
            ReasoningStatusID.COMPLETED,
            ReasoningStatusID.STOPPED,
            ReasoningStatusID.ERROR,
            ReasoningStatusID.MAXED_OUT,
        )
        if session is None or session.status_id in terminal_states:
            dto = ThalamusResponseDTO(
                ok=True, message='No active session to clear.'
            )
            return Response(
                ThalamusResponseSerializer(instance=dto).data,
                status=status.HTTP_200_OK,
            )

        session.status_id = ReasoningStatusID.STOPPED
        session.save(update_fields=['status_id'])
        dto = ThalamusResponseDTO(
            ok=True, message='Session marked STOPPED.'
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

        # Skip STOPPED sessions explicitly: ``/clear/`` flips the
        # current session to STOPPED so the next ``/interact/`` falls
        # through to GENESIS. Until that happens, ``/messages/`` would
        # otherwise hydrate the UI with the just-cleared chat history.
        session = (
            ReasoningSession.objects.filter(spike__spike_train=standing_train)
            .exclude(status_id=ReasoningStatusID.STOPPED)
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

        # 🧹 SHIELD: Sanitize internal system prompts at the source
        clean_messages = []
        for m in messages_payload:
            role = m.get('role')
            content = m.get('content') or m.get('text') or ''

            if role == 'user' and isinstance(content, str):
                if (
                    'YOUR MOVE:' in content
                    or '[SYSTEM DIAGNOSTICS]' in content
                    or '[YOUR CARD CATALOG' in content
                ):
                    continue

            clean_messages.append(m)

        response_dto = ThalamusMessageListDTO(messages=clean_messages)
        return Response(
            ThalamusMessageListSerializer(instance=response_dto).data,
            status=status.HTTP_200_OK,
        )
