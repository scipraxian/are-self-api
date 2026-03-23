import logging
from typing import List

from central_nervous_system.tasks import cast_cns_spell
from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
)
from thalamus.serializers import ThalamusMessageDTO

logger = logging.getLogger(__name__)

ROLE_USER = FrontalLobeConstants.ROLE_USER
ROLE_ASSISTANT = FrontalLobeConstants.ROLE_ASSISTANT


def get_chat_history(
    session: ReasoningSession, include_volatile: bool = False
) -> List[ThalamusMessageDTO]:
    """
    Extracts the conversational history from a ReasoningSession.
    Maps the raw ChatMessage records into the strict ThalamusMessageDTO schema.
    """
    qs = session.turns.filter(model_usage_record__isnull=False).select_related('model_usage_record').order_by('turn_number')

    messages_payload = []
    for turn in qs:
        res = turn.model_usage_record.response_payload or {}
        if isinstance(res, dict):
            content = res.get('content', '') or ''
            if content.strip():
                messages_payload.append(
                    ThalamusMessageDTO(role='assistant', content=content.strip())
                )
    return messages_payload


def inject_human_reply(session: ReasoningSession, user_text: str) -> bool:
    """
    Injects a human's message into a paused ReasoningSession and re-ignites the Cortex.
    Returns True if successful, False if the state was invalid.
    """
    # 1. Validate State
    if session.status_id != ReasoningStatusID.ATTENTION_REQUIRED:
        logger.warning(
            f'Cannot inject reply. Session {session.id} is currently: {session.status_id}'
        )
        return False

    # 2. Find the anchoring turn
    last_turn = session.turns.order_by('-turn_number').first()
    if not last_turn:
        logger.error(f'Cannot inject reply: Session {session.id} has no turns.')
        return False

    from parietal_lobe.models import ToolCall
    ToolCall.objects.create(
        turn=last_turn,
        status_id=ReasoningStatusID.COMPLETED,
        result_payload=f"[HUMAN INTERVENTION]: {user_text.strip()}",
        arguments="{}",
    )

    # 4. Flip the session state back to active natively
    session.status_id = ReasoningStatusID.ACTIVE
    session.save(update_fields=['status_id'])

    # 5. Re-ignite the async execution queue
    cast_cns_spell.delay(session.spike_id)

    # (Note: The Dopamine/Acetylcholine WebSockets will automatically fire
    # here because of the thalamus/signals.py we mapped out earlier).

    return True
