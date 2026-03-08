import asyncio
import html2text
from playwright.async_api import async_playwright


async def mcp_browser_read(url: str) -> str:
    """MCP Tool: Read a webpage and return clean Markdown."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until='networkidle')
                body_html = await page.inner_html('body')

                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                h.ignore_tables = False
                h.bypass_tables = False
                h.escape_snob = True
                markdown = h.handle(body_html)

                if len(markdown) > 15000:
                    markdown = markdown[:15000] + "\n... [Truncated]"
                return markdown
            finally:
                await browser.close()
    except Exception as e:
        return f"Browser read failed: {str(e)}"
