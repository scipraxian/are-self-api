"""Layer 2A: context window compression for long reasoning sessions."""

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from django.db import transaction
from django.db.models import Max

from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
    ReasoningTurnKindID,
)

logger = logging.getLogger(__name__)

ROLE = 'role'
CONTENT = 'content'
ROLE_TOOL = 'tool'
ROLE_SYSTEM = 'system'
ROLE_USER = 'user'
ROLE_ASSISTANT = 'assistant'
NAME = 'name'

# Phase 1 placeholder must stay stable for idempotence checks.
TOOL_PLACEHOLDER_PREFIX = '[Tool call to '

SUMMARY_SENTINEL = '[Conversation summary — prior middle segment]'


def estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token for English text."""
    if not text:
        return 0
    return len(text) // 4


def estimate_message_tokens(message: Dict[str, Any]) -> int:
    """Sum tokens for one chat message (content + tool_calls arguments)."""
    content = message.get(CONTENT)
    total = estimate_tokens(content if isinstance(content, str) else '')
    tool_calls = message.get('tool_calls')
    if tool_calls:
        for tc in tool_calls:
            if isinstance(tc, dict):
                fn = tc.get('function')
                if isinstance(fn, dict):
                    args = fn.get('arguments', '')
                else:
                    args = tc.get('arguments', '')
            else:
                args = ''
            total += estimate_tokens(str(args))
    return total


def estimate_message_list_tokens(messages: Sequence[Dict[str, Any]]) -> int:
    """Total estimated tokens for a message list."""
    return sum(estimate_message_tokens(m) for m in messages)


def _tool_display_name(message: Dict[str, Any]) -> str:
    name = message.get(NAME)
    if name:
        return str(name)
    return 'tool'


def phase1_prune_tool_messages(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Keep first 2 and last 2 tool results; replace middle with placeholders."""
    tool_indices: List[int] = []
    for i, msg in enumerate(messages):
        if msg.get(ROLE) == ROLE_TOOL:
            tool_indices.append(i)
    if len(tool_indices) <= 4:
        return list(messages)

    out = [dict(m) for m in messages]
    keep_set = set(tool_indices[:2] + tool_indices[-2:])
    for idx in tool_indices:
        if idx in keep_set:
            continue
        name = _tool_display_name(out[idx])
        out[idx][CONTENT] = (
            f'{TOOL_PLACEHOLDER_PREFIX}{name} — result summarized]'
        )
    return out


def phase3_aggressive_prune(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Last resort: discard all tool results except the most recent."""
    last_tool_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get(ROLE) == ROLE_TOOL:
            last_tool_idx = i
            break
    if last_tool_idx is None:
        return [dict(m) for m in messages]

    out: List[Dict[str, Any]] = []
    for i, m in enumerate(messages):
        if m.get(ROLE) == ROLE_TOOL and i != last_tool_idx:
            continue
        out.append(dict(m))
    return out


def _middle_segment_for_summary(
    messages: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[int]]:
    """Oldest user/assistant slice between first and last non-system messages."""
    non_system_indices: List[int] = []
    for i, m in enumerate(messages):
        role = m.get(ROLE)
        if role != ROLE_SYSTEM:
            non_system_indices.append(i)
    if len(non_system_indices) <= 2:
        return [], []

    middle_indices = non_system_indices[1:-1]
    segment: List[Dict[str, Any]] = []
    kept_indices: List[int] = []
    for i in middle_indices:
        role = messages[i].get(ROLE)
        if role in (ROLE_USER, ROLE_ASSISTANT):
            segment.append(dict(messages[i]))
            kept_indices.append(i)
    return segment, kept_indices


def _collapse_middle_with_summary(
    messages: List[Dict[str, Any]],
    summary_text: str,
) -> List[Dict[str, Any]]:
    """Replace middle non-system segment with one assistant summary message."""
    non_system_indices: List[int] = []
    for i, m in enumerate(messages):
        if m.get(ROLE) != ROLE_SYSTEM:
            non_system_indices.append(i)
    if len(non_system_indices) <= 2:
        return [dict(m) for m in messages]

    first_ns = non_system_indices[0]
    middle_set = set(non_system_indices[1:-1])

    out: List[Dict[str, Any]] = []
    for m in messages:
        if m.get(ROLE) == ROLE_SYSTEM:
            out.append(dict(m))
    out.append(dict(messages[first_ns]))
    out.append(
        {
            ROLE: ROLE_ASSISTANT,
            CONTENT: f'{SUMMARY_SENTINEL}\n{summary_text}',
        }
    )
    for i in range(len(messages)):
        if messages[i].get(ROLE) == ROLE_SYSTEM:
            continue
        if i <= first_ns:
            continue
        if i in middle_set:
            continue
        out.append(dict(messages[i]))
    return out


def messages_already_summarized(messages: List[Dict[str, Any]]) -> bool:
    """Idempotence: detect prior Phase 2 summary in the message list."""
    for m in messages:
        c = m.get(CONTENT)
        if isinstance(c, str) and c.strip().startswith(SUMMARY_SENTINEL):
            return True
    return False


class ContextCompressor(object):
    """Compresses LLM message lists when approaching the context limit."""

    def __init__(
        self,
        reasoning_session: ReasoningSession,
        model_id: Optional[str] = None,
    ):
        self.reasoning_session = reasoning_session
        self.model_id = model_id

    def compress(
        self,
        messages: List[Dict[str, Any]],
        threshold_tokens: int,
        summarize_fn: Optional[Callable[[str], str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Apply compression phases until under threshold or exhausted.

        summarize_fn: optional sync callable taking concatenated middle text, returns summary.
        """
        current = [dict(m) for m in messages]
        current_tokens = estimate_message_list_tokens(current)
        if current_tokens < threshold_tokens:
            return current

        if messages_already_summarized(current):
            current = phase3_aggressive_prune(current)
            return current

        current = phase1_prune_tool_messages(current)
        current_tokens = estimate_message_list_tokens(current)
        if current_tokens < threshold_tokens:
            logger.info(
                '[ContextCompressor] Phase 1 pruned tool messages for session %s.',
                self.reasoning_session.id,
            )
            return current

        if summarize_fn:
            segment, _ = _middle_segment_for_summary(current)
            if segment:
                concat = '\n'.join(
                    f'{m.get(ROLE)}: {m.get(CONTENT, "")}' for m in segment
                )
                summary = summarize_fn(concat)
                current = _collapse_middle_with_summary(current, summary)
                self._persist_summary_turn(summary)
                current_tokens = estimate_message_list_tokens(current)
                if current_tokens < threshold_tokens:
                    logger.info(
                        '[ContextCompressor] Phase 2 summarized middle for session %s.',
                        self.reasoning_session.id,
                    )
                    return current

        current = phase3_aggressive_prune(current)
        logger.info(
            '[ContextCompressor] Phase 3 aggressive prune for session %s.',
            self.reasoning_session.id,
        )
        return current

    def _persist_summary_turn(self, summary_text: str) -> None:
        """Create audit summary turn and mark prior normal turns compressed."""
        from hypothalamus.models import AIModelProviderUsageRecord

        session = self.reasoning_session
        with transaction.atomic():
            max_num = (
                ReasoningTurn.objects.filter(session=session).aggregate(
                    m=Max('turn_number')
                )['m']
                or 0
            )
            new_num = max_num + 1
            last_turn = session.turns.order_by('-turn_number').first()
            ledger = AIModelProviderUsageRecord.objects.create(
                identity_disc=session.identity_disc,
                request_payload={'summary_of': 'layer2_compression'},
                response_payload={
                    'choices': [
                        {
                            'message': {
                                'role': ROLE_ASSISTANT,
                                'content': summary_text,
                            }
                        }
                    ]
                },
            )
            ReasoningTurn.objects.create(
                session=session,
                turn_number=new_num,
                last_turn=last_turn,
                status_id=ReasoningStatusID.COMPLETED,
                turn_kind_id=ReasoningTurnKindID.SUMMARY,
                is_compressed=False,
                model_usage_record=ledger,
            )
            ReasoningTurn.objects.filter(
                session=session,
                turn_number__lte=max_num,
                turn_kind_id=ReasoningTurnKindID.NORMAL,
            ).update(is_compressed=True)

