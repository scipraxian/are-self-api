"""River-of-Six HISTORY handler — 6 turns of memory with decay/eviction."""
import logging
from typing import Any, Dict, List

from common.constants import HUMAN_TAG, ROLE, USER
from frontal_lobe.models import ReasoningTurn
from identity.addons._handler import IdentityAddonHandler
from parietal_lobe.models import ToolCall

logger = logging.getLogger(__name__)

EVICTION_THRESHOLD = 4
EVICTION_WARNING_AGE = 3
DECAY_WARNING_AGE = 2
EVICTION_WARNING = (
    '\n\n[SYSTEM CRITICAL: L1 EVICTION IMMINENT ON NEXT TURN.'
    ' FINAL CHANCE TO SAVE TO ENGRAMS.]'
)
DECAY_WARNING = '\n\n[SYSTEM WARNING: L1 Cache decay beginning.]'


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


def _build_tool_messages(tool_calls_qs, age):
    if age >= EVICTION_THRESHOLD:
        return []
    messages = []
    for tc in tool_calls_qs:
        content = str(tc.result_payload or '')
        if age == EVICTION_WARNING_AGE:
            content += EVICTION_WARNING
        elif age == DECAY_WARNING_AGE:
            content += DECAY_WARNING
        messages.append(
            {
                'role': 'tool',
                'content': content,
                'tool_call_id': tc.call_id or f'call_{tc.id}',
                'name': tc.tool.name,
            }
        )
    return messages


def _extract_user_messages(req_payload):
    if not req_payload:
        return []
    return [
        m for m in req_payload
        if m.get(ROLE) == USER
        and m.get('content', '').startswith(HUMAN_TAG)
    ]


class RiverOfSix(IdentityAddonHandler):
    def on_history(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
        if not turn or not turn.session:
            return []

        current_turn_num = turn.turn_number
        cutoff_turn = max(1, current_turn_num - 6)

        history_qs = list(
            ReasoningTurn.objects.filter(
                session_id=turn.session.id,
                turn_number__gte=cutoff_turn,
                turn_number__lt=current_turn_num,
                model_usage_record__isnull=False,
            )
            .select_related('model_usage_record')
            .order_by('turn_number')
        )

        history_array = []
        for prev_turn in history_qs:
            age = current_turn_num - prev_turn.turn_number
            tool_calls_qs = list(
                ToolCall.objects.filter(turn=prev_turn)
                .select_related('tool')
                .order_by('id')
            )

            req_payload = prev_turn.model_usage_record.request_payload or []
            history_array.extend(_extract_user_messages(req_payload))

            assistant_msg = _build_assistant_message(prev_turn, tool_calls_qs)
            if assistant_msg:
                if age >= EVICTION_THRESHOLD and 'tool_calls' in assistant_msg:
                    del assistant_msg['tool_calls']
                if assistant_msg.get('content') or 'tool_calls' in assistant_msg:
                    history_array.append(assistant_msg)

            history_array.extend(_build_tool_messages(tool_calls_qs, age))

        return history_array
