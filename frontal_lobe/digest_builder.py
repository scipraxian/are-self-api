"""
Helpers that materialize a ReasoningTurnDigest row from a ReasoningTurn.

Pure functions — no signal mechanics, no side effects outside the single
update_or_create call in build_and_save_digest. All field extractors
handle a fully-formed turn or a partially-populated one (mid-session
saves, missing relations, malformed JSON) without raising into the
caller. Discardable output: re-running the builder on the same turn is
idempotent and produces the same row.

Mirrors the frontend's extractThoughtFromUsageRecord logic so the
backend digest and the UI inspector agree on what "the thought for this
turn" means.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from django.utils.duration import duration_string

from frontal_lobe.models import (
    ReasoningStatus,
    ReasoningTurn,
    ReasoningTurnDigest,
)

logger = logging.getLogger(__name__)


EXCERPT_MAX_LEN: int = 300
TOOL_TARGET_MAX_LEN: int = 120
TOOL_TARGET_KEYS: tuple = ('target', 'path', 'name', 'id', 'file')
MCP_RESPOND_TOOL: str = 'mcp_respond_to_user'
ELLIPSIS: str = '\u2026'


def build_and_save_digest(turn: ReasoningTurn) -> ReasoningTurnDigest:
    """Upsert the digest row for `turn`. Idempotent.

    The caller (the post_save signal) is responsible for deciding
    whether the turn is ready to digest; this function assumes it is
    and builds from whatever is present.
    """
    payload = build_digest_payload(turn)
    digest, _ = ReasoningTurnDigest.objects.update_or_create(
        turn=turn,
        defaults=payload,
    )
    return digest


def build_digest_payload(turn: ReasoningTurn) -> Dict[str, Any]:
    """Assemble the kwargs used to update_or_create the digest row."""
    usage = turn.model_usage_record
    return {
        'session_id': turn.session_id,
        'turn_number': turn.turn_number,
        'status_name': resolve_status_name(turn),
        'model_name': resolve_model_name(usage),
        'tokens_in': usage.input_tokens if usage else 0,
        'tokens_out': usage.output_tokens if usage else 0,
        'excerpt': extract_excerpt(usage),
        'tool_calls_summary': build_tool_calls_summary(turn),
        'engram_ids': build_engram_ids(turn),
    }


def digest_to_vesicle(digest: ReasoningTurnDigest) -> Dict[str, Any]:
    """Serialize a digest to the dict carried in the Acetylcholine vesicle.

    This is the on-wire shape the frontend receives via
    `useDendrite('ReasoningTurnDigest', ...)`. Every field the graph
    and turn-list need to render a node is here, so the UI never has
    to round-trip on a push. Full turn payload (request/response,
    tool args/results) stays behind /api/v2/reasoning_turns/{id}/
    and is only fetched on explicit click.

    Kept symmetrical with build_digest_payload so the DigestSerializer
    (when we build it for the pull-fallback REST endpoint) can reuse
    the same keys without per-transport drift.
    """
    return {
        'turn_id': str(digest.turn_id),
        'session_id': str(digest.session_id),
        'turn_number': digest.turn_number,
        'status_name': digest.status_name,
        'model_name': digest.model_name,
        'tokens_in': digest.tokens_in,
        'tokens_out': digest.tokens_out,
        'excerpt': digest.excerpt,
        'tool_calls_summary': digest.tool_calls_summary,
        'engram_ids': digest.engram_ids,
        'created': digest.created.isoformat() if digest.created else None,
        'modified': (
            digest.modified.isoformat() if digest.modified else None
        ),
        'delta': (
            duration_string(digest.delta) if digest.delta is not None else None
        ),
    }


# ---------------------------------------------------------------------------
# Status and model name
# ---------------------------------------------------------------------------


def resolve_status_name(turn: ReasoningTurn) -> str:
    """Denormalized ReasoningStatus.name, empty string if unreachable."""
    try:
        return turn.status.name or ''
    except AttributeError:
        return ''


def resolve_model_name(usage: Optional[Any]) -> str:
    """Flattened `<usage>.ai_model_provider.ai_model.name`, or ''.

    We traverse four FKs; any missing link returns the empty string
    rather than raising. The digest is a view, not an authority.
    """
    if usage is None:
        return ''
    try:
        return usage.ai_model_provider.ai_model.name or ''
    except AttributeError:
        return ''


# ---------------------------------------------------------------------------
# Excerpt — mirror of frontend extractThoughtFromUsageRecord
# ---------------------------------------------------------------------------


def extract_excerpt(usage: Optional[Any]) -> str:
    """Return up to EXCERPT_MAX_LEN chars of the assistant thought.

    Logic parity with are-self-ui's extractThoughtFromUsageRecord:

        1. Look up the assistant message in the response_payload.
           Handles both direct {role, content, ...} shape and OpenAI
           {choices: [{message: ...}]} shape (CLAUDE.md convention).
        2. If message.content is a non-empty string, use that.
        3. Otherwise walk message.tool_calls for an mcp_respond_to_user
           call and pull the `thought` field out of its arguments JSON.
        4. Otherwise empty string.

    Truncation appends a single U+2026 ellipsis.
    """
    if usage is None:
        return ''
    message = _resolve_assistant_message(usage.response_payload)
    if not message:
        return ''

    content = message.get('content')
    if isinstance(content, str) and content.strip():
        return _truncate(content.strip())

    tool_calls = message.get('tool_calls')
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            thought = _thought_from_respond_call(tc)
            if thought:
                return _truncate(thought)
    return ''


def _resolve_assistant_message(resp: Any) -> Optional[Dict[str, Any]]:
    """Pick the assistant message out of either response_payload shape."""
    if not isinstance(resp, dict):
        return None
    if 'role' in resp:
        return resp
    choices = resp.get('choices')
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        msg = choices[0].get('message')
        return msg if isinstance(msg, dict) else None
    return None


def _thought_from_respond_call(tc: Any) -> str:
    """Pull `thought` from an mcp_respond_to_user tool-call, or ''."""
    if not isinstance(tc, dict):
        return ''
    fn = tc.get('function')
    if not isinstance(fn, dict) or fn.get('name') != MCP_RESPOND_TOOL:
        return ''
    args = fn.get('arguments')
    parsed = _maybe_json(args)
    if not isinstance(parsed, dict):
        return ''
    thought = parsed.get('thought')
    if isinstance(thought, str) and thought.strip():
        return thought.strip()
    return ''


def _maybe_json(value: Any) -> Any:
    """json.loads(value) if it's a string, else return value unchanged."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _truncate(text: str) -> str:
    if len(text) <= EXCERPT_MAX_LEN:
        return text
    return text[:EXCERPT_MAX_LEN - 1].rstrip() + ELLIPSIS


# ---------------------------------------------------------------------------
# Tool calls summary
# ---------------------------------------------------------------------------


def build_tool_calls_summary(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """Collapse the turn's ToolCall rows to {id, tool_name, success, target}.

    Args and result_payload are intentionally excluded — the whole
    point of the digest is to not ship them in list responses. Fetch
    /api/v2/reasoning_turns/{id}/ for the full bodies; the ``id``
    field lets the frontend look up the matching ToolCall on the
    fetched turn by stable pk instead of by array index (index
    matching breaks if a ToolCall is deleted, reordered, or retried).
    """
    summaries: List[Dict[str, Any]] = []
    calls = turn.tool_calls.select_related('tool', 'status').all()
    for call in calls:
        summaries.append({
            'id': str(call.id),
            'tool_name': _tool_name(call),
            'success': _tool_success(call),
            'target': _tool_target(call),
        })
    return summaries


def _tool_name(call: Any) -> str:
    try:
        return call.tool.name or 'unknown'
    except AttributeError:
        return 'unknown'


def _tool_success(call: Any) -> Optional[bool]:
    """Map ReasoningStatus ID to tri-state success.

    True  = COMPLETED
    False = ERROR
    None  = still in flight (Pending, Active, Paused, etc.)
    """
    status_id = getattr(call, 'status_id', None)
    if status_id == ReasoningStatus.IDs.COMPLETED:
        return True
    if status_id == ReasoningStatus.IDs.ERROR:
        return False
    return None


def _tool_target(call: Any) -> str:
    """Best-effort short identifier from the tool arguments.

    Tries a handful of common keys (target, path, name, id, file) in
    order and returns the first string hit, truncated to
    TOOL_TARGET_MAX_LEN. Returns '' if arguments aren't JSON-parsable
    or no key matches. Not authoritative — purely cosmetic.
    """
    raw = getattr(call, 'arguments', '') or ''
    parsed = _maybe_json(raw)
    if not isinstance(parsed, dict):
        return ''
    for key in TOOL_TARGET_KEYS:
        val = parsed.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:TOOL_TARGET_MAX_LEN]
    return ''


# ---------------------------------------------------------------------------
# Engram IDs
# ---------------------------------------------------------------------------


def build_engram_ids(turn: ReasoningTurn) -> List[str]:
    """UUIDs (as strings) of engrams linked to this turn via source_turns.

    Unfiltered — includes inactive engrams. The frontend decides what
    to show; the digest just records what was linked.
    """
    try:
        return [
            str(eid)
            for eid in turn.engrams.values_list('id', flat=True)
        ]
    except AttributeError:
        return []
