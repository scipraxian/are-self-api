"""
Pure helpers to build searchable text from reasoning ledgers (session search).

No I/O; safe for unit tests. Module-level functions only (STYLE_GUIDE.md).
"""
import json
import re
from typing import Any, List, Optional

ROLE_USER = 'user'
ROLE_ASSISTANT = 'assistant'
ROLE_TOOL = 'tool'

HUMAN_TAG_PREFIX = '<<h>>'


def _as_str(obj: Any) -> str:
    if obj is None:
        return ''
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, default=str)
    except TypeError:
        return str(obj)


def iter_request_messages(request_payload: Any) -> List[dict[str, Any]]:
    """Return chat messages from a ledger request_payload (list or OpenAI-style wrapper)."""
    if not request_payload:
        return []
    if isinstance(request_payload, list):
        return [m for m in request_payload if isinstance(m, dict)]
    if isinstance(request_payload, dict):
        inner = request_payload.get('messages')
        if isinstance(inner, list):
            return [m for m in inner if isinstance(m, dict)]
    return []


def extract_user_text_from_request_payload(request_payload: Any) -> str:
    """Concatenate user-role message contents (strip <<h>> tag line prefix when present)."""
    parts: List[str] = []
    for msg in iter_request_messages(request_payload):
        if msg.get('role') != ROLE_USER:
            continue
        raw = _as_str(msg.get('content'))
        if raw.startswith(HUMAN_TAG_PREFIX):
            raw = raw[len(HUMAN_TAG_PREFIX) :].lstrip('\n')
        parts.append(raw)
    return '\n'.join(parts)


def extract_tool_messages_from_request_payload(request_payload: Any) -> str:
    """Concatenate tool-role message contents from the request payload."""
    parts: List[str] = []
    for msg in iter_request_messages(request_payload):
        if msg.get('role') != ROLE_TOOL:
            continue
        parts.append(_as_str(msg.get('content')))
    return '\n'.join(parts)


def extract_assistant_from_response_payload(response_payload: Any) -> str:
    """Assistant text from OpenAI-style response_payload or direct message dict."""
    if not response_payload or not isinstance(response_payload, dict):
        return ''
    choices = response_payload.get('choices')
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get('message')
            if isinstance(message, dict):
                return _as_str(message.get('content'))
    if response_payload.get('role') == ROLE_ASSISTANT:
        return _as_str(response_payload.get('content'))
    return _as_str(response_payload.get('content'))


def extract_assistant_from_request_payload(request_payload: Any) -> str:
    """Assistant messages embedded in the request (e.g. prior turns)."""
    parts: List[str] = []
    for msg in iter_request_messages(request_payload):
        if msg.get('role') != ROLE_ASSISTANT:
            continue
        parts.append(_as_str(msg.get('content')))
    return '\n'.join(parts)


def extract_assistant_corpus(
    request_payload: Any, response_payload: Any
) -> str:
    """All assistant-visible text for role_filter=assistant."""
    parts = [
        extract_assistant_from_response_payload(response_payload),
        extract_assistant_from_request_payload(request_payload),
    ]
    return '\n'.join(p for p in parts if p)


def ledger_combined_search_text(
    request_payload: Any,
    response_payload: Any,
    session_id: Any,
) -> str:
    """Full blob for unfiltered FTS: messages JSON + response + session id string."""
    chunks = [
        _as_str(request_payload),
        _as_str(response_payload),
        str(session_id) if session_id is not None else '',
    ]
    return '\n'.join(c for c in chunks if c)


_WS_SPLIT = re.compile(r'\s+')


def keywords_for_refinement(query: str) -> List[str]:
    """
    Split a user query into loose keywords for Python-side role refinement.

    Strips common boolean tokens; not a full tsquery parser.
    """
    if not query or not query.strip():
        return []
    lowered = query.lower()
    for token in (' and ', ' or ', ' not '):
        lowered = lowered.replace(token, ' ')
    out: List[str] = []
    for part in _WS_SPLIT.split(lowered.strip()):
        if not part:
            continue
        if part in ('and', 'or', 'not'):
            continue
        part = part.strip('"').strip("'")
        if part.endswith('*') and len(part) > 1:
            part = part[:-1]
        if part:
            out.append(part)
    return out


def corpus_matches_keywords(corpus: str, query: str) -> bool:
    """True if every refinement keyword appears in corpus (case-insensitive)."""
    if not corpus:
        return False
    keys = keywords_for_refinement(query)
    if not keys:
        return True
    low = corpus.lower()
    return all(k in low for k in keys)
