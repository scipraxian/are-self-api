import logging
from typing import Any, Dict, List

from common.constants import HUMAN_TAG, ROLE, USER
from frontal_lobe.models import ReasoningTurn
from parietal_lobe.models import ToolCall

logger = logging.getLogger(__name__)


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


def _build_assistant_message(
    prev_turn: ReasoningTurn, tool_calls_qs: list
) -> dict:
    """Build a properly formatted assistant message from atomic sources."""
    res_payload = prev_turn.model_usage_record.response_payload or {}
    assistant_msg = _extract_assistant_message(res_payload)
    if not assistant_msg:
        return {}

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

    return msg


def _build_tool_messages(tool_calls_qs: list) -> List[Dict[str, Any]]:
    """Build tool role messages from ToolCall DB records.

    Normal Chat never evicts or decays — every tool result is replayed
    verbatim for the full session history.
    """
    return [
        {
            'role': 'tool',
            'content': str(tc.result_payload or ''),
            'tool_call_id': tc.call_id or f'call_{tc.id}',
            'name': tc.tool.name,
        }
        for tc in tool_calls_qs
    ]


def _extract_user_messages(req_payload: list) -> List[Dict[str, Any]]:
    """Extract only human-originated user messages from a request_payload.

    Only messages tagged with <<h>> (injected by swarm_message_queue) are
    replayed.  Addon-injected user messages (e.g. prompt_addon) have no tag
    and are skipped — the addon will re-inject them fresh each turn.
    """
    if not req_payload:
        return []
    return [
        m for m in req_payload
        if m.get(ROLE) == USER
        and m.get('content', '').startswith(HUMAN_TAG)
    ]


def normal_chat_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: HISTORY):
    Standard chronological chat history. No eviction, no warnings.

    Reconstructs the entire prior-turn history of this session from atomic,
    non-duplicating sources:
    - request_payload ONLY for <<h>>-tagged user-role messages
    - response_payload for the assistant's message
    - ToolCall DB records for tool results

    Every prior turn in the session is replayed, in chronological order.
    """
    if not turn or not turn.session:
        return []

    current_turn_num = turn.turn_number

    history_qs = list(
        ReasoningTurn.objects.filter(
            session_id=turn.session.id,
            turn_number__lt=current_turn_num,
            model_usage_record__isnull=False,
        )
        .select_related('model_usage_record')
        .order_by('turn_number')
    )

    history_array: List[Dict[str, Any]] = []

    for prev_turn in history_qs:
        # Fetch tool calls from the DB (the single source of truth).
        tool_calls_qs = list(
            ToolCall.objects.filter(turn=prev_turn)
            .select_related('tool')
            .order_by('id')
        )

        # 1. Human user messages (<<h>>-tagged only) from request_payload.
        req_payload = prev_turn.model_usage_record.request_payload or []
        history_array.extend(_extract_user_messages(req_payload))

        # 2. Assistant message built from response_payload + ToolCall records.
        assistant_msg = _build_assistant_message(prev_turn, tool_calls_qs)
        if assistant_msg and (
            assistant_msg.get('content') or 'tool_calls' in assistant_msg
        ):
            history_array.append(assistant_msg)

        # 3. Tool result messages (never evicted).
        history_array.extend(_build_tool_messages(tool_calls_qs))

    return history_array
