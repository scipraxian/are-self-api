from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn
from parietal_lobe.models import ToolCall


def _extract_assistant_message(res_payload: dict) -> dict:
    """Extract the assistant message from a response_payload."""
    if not res_payload:
        return {}
    if 'role' in res_payload:
        return res_payload
    if 'choices' in res_payload:
        for choice in res_payload.get('choices', []):
            msg = choice.get('message', {})
            if msg:
                return msg
    return {}


def normal_chat_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: HISTORY):
    Standard chronological chat history. No eviction, no warnings.

    Reconstructs the last turn from atomic, non-duplicating sources:
    - request_payload ONLY for user-role messages
    - response_payload for the assistant's message
    - ToolCall DB records for tool results
    """
    if not turn or not turn.session:
        return []

    last_turn = (
        ReasoningTurn.objects.filter(
            session_id=turn.session.id,
            turn_number__lt=turn.turn_number,
            model_usage_record__isnull=False,
        )
        .select_related('model_usage_record')
        .order_by('-turn_number')
        .first()
    )

    if not last_turn:
        return []

    history = []

    # 1. Extract user messages from request_payload (only role=user)
    req_payload = last_turn.model_usage_record.request_payload or []
    user_msgs = [m for m in req_payload if m.get('role') == 'user']
    if user_msgs:
        history.append(user_msgs[-1])

    # 2. Build assistant message from response_payload
    res_payload = last_turn.model_usage_record.response_payload or {}
    assistant_msg = _extract_assistant_message(res_payload)

    # 3. Fetch tool calls from the DB
    tool_calls_qs = list(
        ToolCall.objects.filter(turn=last_turn)
        .select_related('tool')
        .order_by('id')
    )

    if assistant_msg:
        msg = {
            'role': 'assistant',
            'content': assistant_msg.get('content', ''),
        }
        if tool_calls_qs:
            msg['tool_calls'] = [
                {
                    'id': tc.call_id or f'call_{tc.id}',
                    'type': 'function',
                    'function': {
                        'name': tc.tool.name,
                        'arguments': tc.arguments or '{}',
                    },
                }
                for tc in tool_calls_qs
            ]
        history.append(msg)

    # 4. Build tool result messages
    for tc in tool_calls_qs:
        history.append({
            'role': 'tool',
            'content': str(tc.result_payload or ''),
            'tool_call_id': tc.call_id or f'call_{tc.id}',
            'name': tc.tool.name,
        })

    return history
