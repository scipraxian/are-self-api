"""Normal chat HISTORY handler — replays full chronological session history."""
import logging
from typing import Any, Dict, List

from common.constants import HUMAN_TAG, ROLE, USER
from frontal_lobe.models import ReasoningTurn
from identity.addons._handler import IdentityAddonHandler
from parietal_lobe.models import ToolCall

logger = logging.getLogger(__name__)


def _extract_assistant_message(res_payload: dict) -> dict:
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


def _build_assistant_message(prev_turn, tool_calls_qs):
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


def _build_tool_messages(tool_calls_qs):
    return [
        {
            'role': 'tool',
            'content': str(tc.result_payload or ''),
            'tool_call_id': tc.call_id or f'call_{tc.id}',
            'name': tc.tool.name,
        }
        for tc in tool_calls_qs
    ]


def _extract_user_messages(req_payload):
    if not req_payload:
        return []
    return [
        m for m in req_payload
        if m.get(ROLE) == USER
        and m.get('content', '').startswith(HUMAN_TAG)
    ]


class NormalChat(IdentityAddonHandler):
    def on_history(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
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
            tool_calls_qs = list(
                ToolCall.objects.filter(turn=prev_turn)
                .select_related('tool')
                .order_by('id')
            )

            req_payload = prev_turn.model_usage_record.request_payload or []
            history_array.extend(_extract_user_messages(req_payload))

            assistant_msg = _build_assistant_message(prev_turn, tool_calls_qs)
            if assistant_msg and (
                assistant_msg.get('content') or 'tool_calls' in assistant_msg
            ):
                history_array.append(assistant_msg)

            history_array.extend(_build_tool_messages(tool_calls_qs))

        return history_array
