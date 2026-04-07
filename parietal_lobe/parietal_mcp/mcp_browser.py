"""
Headless browser control (Playwright). `ref` is treated as a CSS selector string.
"""
import json
import logging
import os
import tempfile
from typing import Any, Dict

logger = logging.getLogger(__name__)

_playwright = None
_browser = None
_pages: Dict[str, Any] = {}


async def _ensure_browser():
    global _playwright, _browser
    from playwright.async_api import async_playwright

    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
    return _browser


async def _get_page(session_key: str):
    browser = await _ensure_browser()
    if session_key not in _pages:
        _pages[session_key] = await browser.new_page()
    return _pages[session_key]


async def mcp_browser(
    action: str,
    session_id: str = '',
    turn_id: str = '',
    url: str = '',
    ref: str = '',
    text: str = '',
    key: str = '',
    direction: str = 'down',
    question: str = '',
) -> Dict[str, Any]:
    """Dispatch browser actions for the current reasoning session."""
    session_key = session_id or 'default'
    action = (action or '').strip().lower()

    if action == 'navigate':
        page = await _get_page(session_key)
        await page.goto(url, wait_until='networkidle', timeout=30000)
        title = await page.title()
        snap = await _snapshot_text(page)
        return {'title': title, 'url': page.url, 'snapshot': snap}

    if action == 'snapshot':
        page = await _get_page(session_key)
        snap = await _snapshot_text(page)
        title = await page.title()
        return {'snapshot': snap, 'title': title, 'url': page.url}

    if action == 'click':
        page = await _get_page(session_key)
        await page.click(ref, timeout=10000)
        snap = await _snapshot_text(page)
        return {'success': True, 'snapshot': snap}

    if action == 'type':
        page = await _get_page(session_key)
        await page.fill(ref, text, timeout=10000)
        return {'success': True}

    if action == 'press':
        page = await _get_page(session_key)
        await page.keyboard.press(key)
        snap = await _snapshot_text(page)
        return {'success': True, 'snapshot': snap}

    if action == 'scroll':
        page = await _get_page(session_key)
        delta = 600 if direction.lower() == 'down' else -600
        await page.mouse.wheel(0, delta)
        snap = await _snapshot_text(page)
        return {'snapshot': snap}

    if action == 'back':
        page = await _get_page(session_key)
        await page.go_back()
        return {'url': page.url, 'title': await page.title()}

    if action == 'get_images':
        page = await _get_page(session_key)
        imgs = await page.evaluate(
            """() => Array.from(document.images).map((e, i) => ({
                url: e.src,
                alt: e.alt || '',
                ref: 'img:nth-of-type(' + (i + 1) + ')'
            }))""",
        )
        return {'images': imgs}

    if action == 'vision':
        page = await _get_page(session_key)
        png = await page.screenshot()
        path = None
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp.write(png)
            path = tmp.name
        from parietal_lobe.parietal_mcp.mcp_vision import mcp_vision as run_vision

        try:
            result = await run_vision(path, question)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return {'analysis': result.get('analysis', ''), 'provider': result.get('provider', '')}

    return {'error': 'Unknown action: %s' % action}


async def _snapshot_text(page) -> str:
    try:
        snap = await page.accessibility.snapshot()
        return json.dumps(snap, indent=2)[:20000]
    except Exception as exc:
        logger.warning('[mcp_browser] snapshot failed: %s', exc)
        return await page.content()
