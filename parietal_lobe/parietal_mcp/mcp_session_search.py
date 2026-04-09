"""
Search past reasoning sessions: ToolCall rows and ReasoningTurn ledgers (PostgreSQL FTS).

On PostgreSQL, queries use ``SearchQuery(..., search_type='websearch')`` (plain words,
quoted phrases, ``or``, ``-`` negation). Falls back to icontains-style matching on SQLite.
"""
import logging
from typing import Any, Dict, List, Optional

from asgiref.sync import sync_to_async
from django.db import connection
from django.db.models import Q, TextField
from django.db.models.functions import Cast

from parietal_lobe.models import ToolCall

from parietal_lobe.parietal_mcp.mcp_session_search_extract import (
    corpus_matches_keywords,
    extract_assistant_corpus,
    extract_tool_messages_from_request_payload,
    extract_user_text_from_request_payload,
    keywords_for_refinement,
    ledger_combined_search_text,
)

logger = logging.getLogger(__name__)

SESSION_SEARCH_MAX_LIMIT = 10
# Candidate cap before Python role refinement (PostgreSQL).
_LEDGER_REFINE_CAP = 200


def _snippet(text: str, max_len: int = 500) -> str:
    if not text:
        return ''
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len]


def _turn_timestamp(turn: Any) -> str:
    created = getattr(turn, 'created', None)
    if created:
        return created.isoformat()
    return ''


def _merge_and_limit(
    rows: List[Dict[str, Any]], limit: int
) -> List[Dict[str, Any]]:
    rows.sort(key=lambda r: float(r.get('score') or 0.0), reverse=True)
    return rows[:limit]


def _search_toolcall_postgres(
    query: str,
    sq: Any,
    limit: int,
) -> List[Dict[str, Any]]:
    from django.contrib.postgres.search import SearchRank, SearchVector

    vector = SearchVector('arguments', 'result_payload')
    qs = (
        ToolCall.objects.annotate(search=vector, rank=SearchRank(vector, sq))
        .filter(search=sq)
        .select_related('turn', 'turn__session')
        .order_by('-rank')[:limit]
    )
    out: List[Dict[str, Any]] = []
    for tc in qs:
        blob = '%s %s' % (tc.arguments or '', tc.result_payload or '')
        out.append(
            {
                'session_id': str(tc.turn.session_id),
                'turn_number': tc.turn.turn_number,
                'content_snippet': _snippet(blob),
                'timestamp': _turn_timestamp(tc.turn),
                'score': float(tc.rank) if tc.rank is not None else 0.0,
                'role': 'tool',
            }
        )
    return out


def _search_toolcall_sqlite(query: str, limit: int) -> List[Dict[str, Any]]:
    keys = keywords_for_refinement(query)
    qs = ToolCall.objects.select_related('turn', 'turn__session').all()
    if keys:
        for k in keys:
            qs = qs.filter(
                Q(arguments__icontains=k) | Q(result_payload__icontains=k)
            )
    else:
        qs = qs.none()
    out: List[Dict[str, Any]] = []
    for tc in qs.order_by('-turn__turn_number')[:limit]:
        blob = '%s %s' % (tc.arguments or '', tc.result_payload or '')
        out.append(
            {
                'session_id': str(tc.turn.session_id),
                'turn_number': tc.turn.turn_number,
                'content_snippet': _snippet(blob),
                'timestamp': _turn_timestamp(tc.turn),
                'score': 0.5,
                'role': 'tool',
            }
        )
    return out


def _refine_ledger_turn(
    turn: Any,
    role_filter: Optional[str],
    query: str,
) -> Optional[str]:
    """Return role-specific corpus for refinement, or None if no usage record."""
    ur = turn.model_usage_record
    if not ur:
        return None
    req = ur.request_payload
    resp = ur.response_payload
    if role_filter == 'user':
        return extract_user_text_from_request_payload(req)
    if role_filter == 'assistant':
        return extract_assistant_corpus(req, resp)
    if role_filter == 'tool':
        return extract_tool_messages_from_request_payload(req)
    return ledger_combined_search_text(req, resp, turn.session_id)


def _search_ledger_postgres(
    query: str,
    sq: Any,
    role_filter: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    from django.contrib.postgres.search import SearchRank, SearchVector
    from frontal_lobe.models import ReasoningTurn

    vector = SearchVector(
        Cast('model_usage_record__request_payload', TextField()),
        Cast('model_usage_record__response_payload', TextField()),
        Cast('session_id', TextField()),
    )
    qs = (
        ReasoningTurn.objects.exclude(model_usage_record_id__isnull=True)
        .annotate(search=vector, rank=SearchRank(vector, sq))
        .filter(search=sq)
        .select_related('session', 'model_usage_record')
        .order_by('-rank')[:_LEDGER_REFINE_CAP]
    )
    out: List[Dict[str, Any]] = []
    for turn in qs:
        corpus = _refine_ledger_turn(turn, role_filter, query)
        if corpus is None:
            continue
        if role_filter in ('user', 'assistant', 'tool'):
            if not corpus_matches_keywords(corpus, query):
                continue
        if role_filter == 'user':
            role_label = 'user'
        elif role_filter == 'tool':
            role_label = 'tool'
        elif role_filter == 'assistant':
            role_label = 'assistant'
        else:
            role_label = 'mixed'
        out.append(
            {
                'session_id': str(turn.session_id),
                'turn_number': turn.turn_number,
                'content_snippet': _snippet(corpus),
                'timestamp': _turn_timestamp(turn),
                'score': float(turn.rank) if turn.rank is not None else 0.0,
                'role': role_label,
            }
        )
        if len(out) >= limit:
            break
    return out


def _search_ledger_sqlite(
    query: str,
    role_filter: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    from frontal_lobe.models import ReasoningTurn

    keys = keywords_for_refinement(query)
    qs = ReasoningTurn.objects.exclude(
        model_usage_record_id__isnull=True
    ).select_related('session', 'model_usage_record')
    if keys:
        for k in keys:
            qs = qs.filter(
                Q(model_usage_record__request_payload__icontains=k)
                | Q(model_usage_record__response_payload__icontains=k)
                | Q(session_id__icontains=k)
            )
    else:
        qs = qs.none()
    out: List[Dict[str, Any]] = []
    for turn in qs.order_by('-turn_number')[: _LEDGER_REFINE_CAP]:
        corpus = _refine_ledger_turn(turn, role_filter, query)
        if corpus is None:
            continue
        if role_filter in ('user', 'assistant', 'tool'):
            if not corpus_matches_keywords(corpus, query):
                continue
        role_label = 'user' if role_filter == 'user' else (
            'assistant' if role_filter == 'assistant' else (
                'tool' if role_filter == 'tool' else 'mixed'
            )
        )
        out.append(
            {
                'session_id': str(turn.session_id),
                'turn_number': turn.turn_number,
                'content_snippet': _snippet(corpus),
                'timestamp': _turn_timestamp(turn),
                'score': 0.45,
                'role': role_label,
            }
        )
        if len(out) >= limit:
            break
    return out


def _normalize_role_filter(role_filter: Optional[str]) -> Optional[str]:
    if not role_filter:
        return None
    r = role_filter.strip().lower()
    if r in ('user', 'assistant', 'tool'):
        return r
    return None


def _session_search_sync(
    query: str,
    limit: int,
    role_filter: Optional[str],
) -> Dict[str, Any]:
    limit = min(max(1, int(limit)), SESSION_SEARCH_MAX_LIMIT)
    rf = _normalize_role_filter(role_filter)
    q = (query or '').strip()
    if not q:
        return {'matches': [], 'query': query, 'count': 0}

    matches: List[Dict[str, Any]] = []

    if connection.vendor == 'postgresql':
        from django.contrib.postgres.search import SearchQuery

        try:
            sq = SearchQuery(q, search_type='websearch', config='english')
        except ValueError as exc:
            logger.warning('[mcp_session_search] Invalid query: %s', exc)
            return {'matches': [], 'query': query, 'count': 0}

        try:
            if rf is None:
                matches.extend(_search_toolcall_postgres(q, sq, limit))
                matches.extend(_search_ledger_postgres(q, sq, None, limit))
            elif rf == 'tool':
                matches.extend(_search_toolcall_postgres(q, sq, limit))
                matches.extend(_search_ledger_postgres(q, sq, 'tool', limit))
            elif rf == 'user':
                matches.extend(_search_ledger_postgres(q, sq, 'user', limit))
            elif rf == 'assistant':
                matches.extend(_search_ledger_postgres(q, sq, 'assistant', limit))
        except Exception as exc:
            logger.warning('[mcp_session_search] PostgreSQL FTS failed: %s', exc)
            matches = _session_search_sqlite_fallback(q, limit, rf)
            return {
                'matches': matches,
                'query': query,
                'count': len(matches),
            }
    else:
        matches = _session_search_sqlite_fallback(q, limit, rf)

    matches = _merge_and_limit(matches, limit)
    return {'matches': matches, 'query': query, 'count': len(matches)}


def _session_search_sqlite_fallback(
    query: str,
    limit: int,
    role_filter: Optional[str],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    if role_filter is None:
        merged.extend(_search_toolcall_sqlite(query, limit))
        merged.extend(_search_ledger_sqlite(query, None, limit))
    elif role_filter == 'tool':
        merged.extend(_search_toolcall_sqlite(query, limit))
        merged.extend(_search_ledger_sqlite(query, 'tool', limit))
    elif role_filter == 'user':
        merged.extend(_search_ledger_sqlite(query, 'user', limit))
    elif role_filter == 'assistant':
        merged.extend(_search_ledger_sqlite(query, 'assistant', limit))
    return _merge_and_limit(merged, limit)


async def mcp_session_search(
    query: str,
    limit: int = 5,
    role_filter: Optional[str] = None,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Search ToolCall rows and ReasoningTurn ledgers (FTS on PostgreSQL)."""
    return await sync_to_async(_session_search_sync)(query, limit, role_filter)
