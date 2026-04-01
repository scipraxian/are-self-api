import json
import logging
from typing import Any, Dict, List

from central_nervous_system.tasks import fire_spike
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

                # 🧹 SHIELD: Sanitize internal system prompts at the source
                if isinstance(last_user_msg, str):
                    if (
                        'YOUR MOVE:' in last_user_msg
                        or '[SYSTEM DIAGNOSTICS]' in last_user_msg
                        or '[YOUR CARD CATALOG' in last_user_msg
                    ):
                        last_user_msg = ''

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
                    # ... inside the choices loop ...
                    message = choice.get('message', {})
                    content = message.get('content', '') or ''
                    tool_calls = message.get('tool_calls', [])

                    # 1. Grab native reasoning if the model supports it out of the box
                    reasoning = message.get('reasoning_content', '') or ''
                    if not reasoning:
                        provider_fields = message.get(
                            'provider_specific_fields', {}
                        )
                        reasoning = (
                            provider_fields.get('reasoning_content', '') or ''
                        )

                    # 2. FLATTEN TOOL CALLS
                    if tool_calls:
                        for tool in tool_calls:
                            try:
                                func_name = tool.get('function', {}).get(
                                    'name', ''
                                )
                                args_str = tool.get('function', {}).get(
                                    'arguments', '{}'
                                )
                                args = json.loads(args_str)

                                if func_name == 'mcp_ask_user':
                                    extracted_msg = args.get('message', '')
                                    if extracted_msg:
                                        content += f'\n{extracted_msg}'

                                elif func_name in (
                                    'mcp_internal_monologue',
                                    'mcp_respond_to_user',
                                ):
                                    # Route the user message to standard content
                                    extracted_msg = args.get(
                                        'message_to_user', ''
                                    )
                                    if extracted_msg:
                                        content += f'\n{extracted_msg}'

                                    # Route the thought to the reasoning block for assistant-ui!
                                    extracted_thought = args.get('thought', '')
                                    if extracted_thought:
                                        reasoning += f'\n{extracted_thought}'

                            except json.JSONDecodeError:
                                continue
                            except Exception as e:
                                logger.warning(
                                    f'Error parsing tool call in history: {e}'
                                )
                                continue

                    content = content.strip()
                    reasoning = reasoning.strip()

                    # 3. Build the strict Vercel AI SDK 'parts' array
                    parts = []

                    # This triggers the thought bubble in assistant-ui
                    if reasoning:
                        parts.append({'type': 'reasoning', 'text': reasoning})

                    # This is the standard text output
                    if content:
                        parts.append({'type': 'text', 'text': content})

                    # If we have any parts, append the pristine message object
                    if parts:
                        messages_payload.append(
                            {
                                'role': 'assistant',
                                'content': content,
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
        fire_spike.delay(session.spike_id)
    else:
        # If it's already running, just save the queue. It will catch it next turn.
        session.save(update_fields=['swarm_message_queue'])

    return True
