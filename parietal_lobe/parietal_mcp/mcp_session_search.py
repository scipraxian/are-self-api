"""
Search past reasoning sessions and tool payloads (PostgreSQL FTS when available).
"""
import json
import logging
from typing import Any, Dict, List, Optional

from asgiref.sync import sync_to_async
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import connection
from django.db.models import Q

from parietal_lobe.models import ToolCall

logger = logging.getLogger(__name__)


def _text_from_json(obj: Any) -> str:
    if obj is None:
        return ''
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj)
    except TypeError:
        return str(obj)


def _search_postgres(query: str, limit: int, role_filter: Optional[str]) -> List[Dict[str, Any]]:
    vector = SearchVector('arguments', 'result_payload')
    sq = SearchQuery(query)
    qs = (
        ToolCall.objects.annotate(search=vector)
        .filter(search=sq)
        .select_related('turn', 'turn__session')
        .order_by('turn__session_id', '-turn__turn_number')[:limit]
    )
    matches = []
    for tc in qs:
        if role_filter and role_filter not in ('tool',):
            continue
        snippet = (tc.result_payload or tc.arguments or '')[:500]
        matches.append(
            {
                'session_id': str(tc.turn.session_id),
                'turn_number': tc.turn.turn_number,
                'content_snippet': snippet,
                'timestamp': tc.turn.created.isoformat()
                if hasattr(tc.turn, 'created')
                else '',
                'score': 1.0,
            }
        )
    return matches


def _search_fallback(query: str, limit: int, role_filter: Optional[str]) -> List[Dict[str, Any]]:
    q = Q(arguments__icontains=query) | Q(result_payload__icontains=query)
    qs = (
        ToolCall.objects.filter(q)
        .select_related('turn', 'turn__session')
        .order_by('-turn__turn_number')[:limit]
    )
    matches = []
    for tc in qs:
        if role_filter and role_filter not in ('tool',):
            continue
        snippet = (tc.result_payload or tc.arguments or '')[:500]
        matches.append(
            {
                'session_id': str(tc.turn.session_id),
                'turn_number': tc.turn.turn_number,
                'content_snippet': snippet,
                'timestamp': tc.turn.created.isoformat()
                if hasattr(tc.turn, 'created')
                else '',
                'score': 0.5,
            }
        )
    return matches


def _session_search_sync(
    query: str,
    limit: int,
    role_filter: Optional[str],
) -> Dict[str, Any]:
    limit = min(max(1, int(limit)), 10)
    if connection.vendor == 'postgresql':
        try:
            matches = _search_postgres(query, limit, role_filter)
        except Exception as exc:
            logger.warning('[mcp_session_search] FTS failed: %s', exc)
            matches = _search_fallback(query, limit, role_filter)
    else:
        matches = _search_fallback(query, limit, role_filter)

    return {'matches': matches, 'query': query, 'count': len(matches)}


async def mcp_session_search(
    query: str,
    limit: int = 5,
    role_filter: Optional[str] = None,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Full-text search over tool call text and related session metadata."""
    return await sync_to_async(_session_search_sync)(query, limit, role_filter)
