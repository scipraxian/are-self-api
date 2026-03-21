import logging
from typing import List

from central_nervous_system.tasks import cast_cns_spell
from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.models import (
    ChatMessage,
    ChatMessageRole,
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
    # Base queryset: only grab human and AI messages, ordered chronologically
    qs = (
        ChatMessage.objects.filter(
            session=session, role__name__in=[ROLE_USER, ROLE_ASSISTANT]
        )
        .select_related(ChatMessage.ROLE_KEY)
        .order_by('created')
    )

    # Filter out system/volatile noise unless explicitly requested
    if not include_volatile:
        qs = qs.filter(is_volatile=False)

    messages_payload = []
    for msg in qs:
        if msg.content and msg.content.strip():
            # DTO expects lowercase 'user' or 'assistant'
            role_name = msg.role.name.lower()
            messages_payload.append(
                ThalamusMessageDTO(role=role_name, content=msg.content.strip())
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

    # 3. Save the human memory
    # Note: is_volatile defaults to False, ensuring it shows up in the UI
    ChatMessage.objects.create(
        session=session,
        turn=last_turn,
        role_id=ChatMessageRole.USER,
        content=user_text.strip(),
    )

    # 4. Flip the session state back to active natively
    session.status_id = ReasoningStatusID.ACTIVE
    session.save(update_fields=['status_id'])

    # 5. Re-ignite the async execution queue
    cast_cns_spell.delay(session.spike_id)

    # (Note: The Dopamine/Acetylcholine WebSockets will automatically fire
    # here because of the thalamus/signals.py we mapped out earlier).

    return True
