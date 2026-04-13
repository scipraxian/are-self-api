"""
Web search via SearXNG or Tavily.
"""
import asyncio
import logging
import os
from typing import Any, Dict, List
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)

TAVILY_URL = 'https://api.tavily.com/search'


def _searxng(query: str, max_results: int) -> Dict[str, Any]:
    base = os.environ.get('SEARXNG_URL', '').rstrip('/')
    if not base:
        return {}
    url = '%s/search?q=%s&format=json&categories=general' % (
        base,
        quote_plus(query),
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    results: List[Dict[str, str]] = []
    for item in data.get('results', [])[:max_results]:
        results.append(
            {
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'snippet': item.get('content', '') or item.get('snippet', ''),
            }
        )
    return {'results': results, 'query': query, 'count': len(results)}

# TODO: Delete this API integration - AI slop
def _tavily(query: str, max_results: int) -> Dict[str, Any]:
    key = os.environ.get('TAVILY_API_KEY', '')
    if not key:
        return {}
    response = requests.post(
        TAVILY_URL,
        json={'api_key': key, 'query': query, 'max_results': max_results},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    results = []
    for item in data.get('results', [])[:max_results]:
        results.append(
            {
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'snippet': item.get('content', '') or '',
            }
        )
    return {'results': results, 'query': query, 'count': len(results)}


def _run_search(query: str, max_results: int) -> Dict[str, Any]:
    if os.environ.get('SEARXNG_URL'):
        try:
            return _searxng(query, max_results)
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.warning('[mcp_web_search] SearXNG failed: %s', exc)
    if os.environ.get('TAVILY_API_KEY'):
        try:
            return _tavily(query, max_results)
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.warning('[mcp_web_search] Tavily failed: %s', exc)
    return {
        'error': (
            'No search provider configured. Set SEARXNG_URL or TAVILY_API_KEY.'
        ),
        'results': [],
        'query': query,
        'count': 0,
    }


async def mcp_web_search(
    query: str,
    max_results: int = 5,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Search the web using SearXNG (preferred) or Tavily."""
    max_results = min(int(max_results), 20)
    return await asyncio.to_thread(_run_search, query, max_results)
