import logging
from typing import Any, Dict, List

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
) -> List[Dict[str, Any]]:
    """
    Extracts the conversational history from a ReasoningSession.
    Uses the Vercel AI SDK 'parts' schema to natively trigger
    assistant-ui's ChainOfThought primitives.
    """
    qs = (
        session.turns.filter(model_usage_record__isnull=False)
        .select_related('model_usage_record')
        .order_by('turn_number')
    )

    messages_payload = []
    for turn in qs:
        # 1. Extract the User Prompt
        req = turn.model_usage_record.request_payload or []
        if isinstance(req, list):
            user_messages = [m for m in req if m.get('role') == 'user']
            if user_messages:
                last_user_msg = user_messages[-1].get('content', '')
                if last_user_msg:
                    messages_payload.append(
                        {'role': 'user', 'content': last_user_msg.strip()}
                    )

        # 2. Extract Assistant Choices and format into AI SDK 'parts'
        res = turn.model_usage_record.response_payload or {}
        if isinstance(res, dict):
            choices = res.get('choices', [])

            if choices and isinstance(choices, list):
                for choice in choices:
                    message = choice.get('message', {})
                    content = message.get('content', '') or ''

                    # Extract native reasoning
                    reasoning = message.get('reasoning_content', '') or ''
                    if not reasoning:
                        provider_fields = message.get(
                            'provider_specific_fields', {}
                        )
                        reasoning = (
                            provider_fields.get('reasoning_content', '') or ''
                        )

                    # Build the strict Vercel AI SDK 'parts' array
                    parts = []

                    if reasoning.strip():
                        parts.append(
                            {'type': 'reasoning', 'text': reasoning.strip()}
                        )

                    if content.strip():
                        parts.append({'type': 'text', 'text': content.strip()})

                    # If we have any parts, append the pristine message object
                    if parts:
                        messages_payload.append(
                            {
                                'role': 'assistant',
                                'content': content.strip(),
                                # Fallback for base content
                                'parts': parts,
                            }
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
