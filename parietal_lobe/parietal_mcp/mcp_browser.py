"""
Headless browser control (Playwright) with @eN accessibility-style refs for humans.

``ref`` may be ``@e12`` / ``e12`` (injected ``data-parietal-browser-ref``) or a CSS selector.
"""
import logging
import os
import re
import tempfile
from typing import Any, Dict

logger = logging.getLogger(__name__)

NAVIGATION_TIMEOUT_MS = 30_000
INTERACTION_TIMEOUT_MS = 10_000
SNAPSHOT_MAX_CHARS = 20_000
BROWSER_REF_ATTR = 'data-parietal-browser-ref'

# @e + one or more digits and nothing before or after
REF_TOKEN_RE = re.compile(r'^@?e(\d+)$', re.IGNORECASE)

_playwright = None
_browser = None
_pages: Dict[str, Any] = {}


async def _ensure_browser():
    """
    Ensure Playwright browser is initialized and return it.
    """
    global _playwright, _browser
    from playwright.async_api import async_playwright

    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
    return _browser


async def _get_page(session_key: str):
    """
    Retrieve or create a Playwright page for the given session key.
    """
    if session_key not in _pages:
        browser = await _ensure_browser()
        _pages[session_key] = await browser.new_page()
    return _pages[session_key]


async def inject_ref_markers(page: Any) -> int:
    """Assign sequential ``data-parietal-browser-ref`` markers to interactive nodes."""
    count = await page.evaluate(
        """() => {
          const sel = [
            'a[href]', 'button', 'input', 'textarea', 'select',
            '[role="button"]', 'img', '[tabindex]:not([tabindex="-1"])'
          ].join(',');
          const nodes = Array.from(document.querySelectorAll(sel));
          let i = 1;
          for (const el of nodes) {
            el.setAttribute('data-parietal-browser-ref', String(i++));
          }
          return i - 1;
        }""",
    )
    return int(count or 0)


def _locator_for_ref(page: Any, ref: str) -> Any:
    ref = (ref or '').strip()
    ref_match = REF_TOKEN_RE.match(ref)
    if ref_match:
        idx = ref_match.group(1)
        return page.locator('[%s="%s"]' % (BROWSER_REF_ATTR, idx))
    return page.locator(ref)


async def _snapshot_text(page: Any) -> str:
    """Human-readable lines ``@eN tag …`` after injecting ref markers."""
    try:
        await inject_ref_markers(page)
        lines = await page.evaluate(
            """() => {
              const els = Array.from(document.querySelectorAll('[data-parietal-browser-ref]'));
              return els.map((el) => {
                const id = el.getAttribute('data-parietal-browser-ref');
                const tag = el.tagName.toLowerCase();
                const name = el.getAttribute('aria-label') || el.getAttribute('alt')
                  || el.getAttribute('placeholder') || el.getAttribute('name') || '';
                let text = (el.innerText || '').trim();
                if (text.length > 120) text = text.slice(0, 117) + '...';
                return '@e' + id + ' ' + tag + ' name=' + JSON.stringify(name) + ' text=' + JSON.stringify(text);
              });
            }""",
        )
        blob = '\n'.join(lines) if lines else ''
        if len(blob) > SNAPSHOT_MAX_CHARS:
            return blob[:SNAPSHOT_MAX_CHARS]
        return blob
    except Exception as exc:
        logger.warning('[mcp_browser] snapshot failed: %s', exc)
        try:
            content = await page.content()
            return content[:SNAPSHOT_MAX_CHARS]
        except Exception as inner:
            logger.warning('[mcp_browser] content fallback failed: %s', inner)
            return ''


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
    """
    MCP Tool: Dispatch browser actions for the current reasoning session.
    """
    session_key = session_id or 'default'
    action = (action or '').strip().lower()

    if action == 'close':
        if session_key in _pages:
            pg = _pages[session_key]
            try:
                await pg.close()
            except Exception as exc:
                logger.warning('[mcp_browser] page close failed: %s', exc)
            del _pages[session_key]
        return {'success': True, 'closed': True}

    if action == 'navigate':
        page = await _get_page(session_key)
        await page.goto(
            url,
            wait_until='networkidle',
            timeout=NAVIGATION_TIMEOUT_MS,
        )
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
        loc = _locator_for_ref(page, ref)
        await loc.click(timeout=INTERACTION_TIMEOUT_MS)
        snap = await _snapshot_text(page)
        return {'success': True, 'snapshot': snap}

    if action == 'type':
        page = await _get_page(session_key)
        loc = _locator_for_ref(page, ref)
        await loc.fill(text, timeout=INTERACTION_TIMEOUT_MS)
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
        await page.go_back(timeout=NAVIGATION_TIMEOUT_MS)
        return {'url': page.url, 'title': await page.title()}

    if action == 'get_images':
        page = await _get_page(session_key)
        await inject_ref_markers(page)
        imgs = await page.evaluate(
            """() => Array.from(document.images).map((img) => {
              const r = img.getAttribute('data-parietal-browser-ref');
              return {
                url: img.src,
                alt: img.alt || '',
                ref: r ? ('@e' + r) : ''
              };
            })""",
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
        except TimeoutError as exc:
            result = {'analysis': str(exc), 'provider': ''}
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return {
            'analysis': result.get('analysis', ''),
            'provider': result.get('provider', ''),
        }

    return {'error': 'Unknown action: %s' % action}
