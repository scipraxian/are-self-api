"""
Fetch URL and extract readable text (trafilatura with html2text fallback).
"""
import logging
from typing import Any, Dict
from urllib.parse import urlparse

import html2text
import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30


def _extract_sync(url: str, max_length: int) -> Dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return {'error': 'Only http/https URLs are supported.', 'url': url}

    try:
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {'error': str(exc), 'url': url}

    raw = response.text
    title = ''
    content = ''

    try:
        import trafilatura

        extracted = trafilatura.extract(
            raw,
            include_comments=False,
            include_tables=True,
            url=url,
        )
        if extracted:
            content = extracted
        meta = trafilatura.extract_metadata(raw)
        if meta and meta.title:
            title = meta.title
    except Exception as exc:
        logger.info('[mcp_web_extract] trafilatura failed: %s', exc)

    if not content:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        content = h.handle(raw)

    if not title:
        title = url

    truncated = len(content) > max_length
    if truncated:
        content = content[:max_length]

    return {
        'url': url,
        'title': title,
        'content': content,
        'truncated': truncated,
        'char_count': len(content),
    }


async def mcp_web_extract(
    url: str,
    max_length: int = 10000,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Extract main text from a URL."""
    from asgiref.sync import sync_to_async

    return await sync_to_async(_extract_sync)(url, int(max_length))
