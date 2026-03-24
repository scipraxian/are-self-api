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
    qs = (
        session.turns.filter(model_usage_record__isnull=False)
        .select_related('model_usage_record')
        .order_by('turn_number')
    )

    messages_payload = []
    for turn in qs:
        res = turn.model_usage_record.response_payload or {}
        if isinstance(res, dict):
            content = res.get('content', '') or ''
            if content.strip():
                messages_payload.append(
                    ThalamusMessageDTO(
                        role='assistant', content=content.strip()
                    )
                )
    return messages_payload


def inject_swarm_chatter(
    session: ReasoningSession, role: str, text: str
) -> bool:
    """
    Drops an async message into the AI's queue. Wakes the AI if it was waiting.
    """
    # 1. Drop the message in the queue
    queue = session.swarm_message_queue or []
    queue.append({'role': role, 'content': text.strip()})
    session.swarm_message_queue = queue

    # 2. If it was asleep, wake it up and ring the bell
    if session.status_id == ReasoningStatusID.ATTENTION_REQUIRED:
        session.status_id = ReasoningStatusID.ACTIVE
        session.save(update_fields=['swarm_message_queue', 'status_id'])
        cast_cns_spell.delay(session.spike_id)
    else:
        # If it's already running, just save the queue. It will catch it next turn.
        session.save(update_fields=['swarm_message_queue'])

    return True
