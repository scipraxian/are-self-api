import asyncio
from playwright.async_api import async_playwright


async def mcp_browser_search(query: str) -> str:
    """MCP Tool: Search the web using DuckDuckGo."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(f'https://html.duckduckgo.com/html/?q={query}')

                results = []
                # DuckDuckGo HTML version elements
                elements = await page.query_selector_all('.result')
                for i, el in enumerate(elements[:5]):
                    title_el = await el.query_selector('.result__title')
                    url_el = await el.query_selector('.result__url')
                    snippet_el = await el.query_selector('.result__snippet')

                    if title_el and url_el and snippet_el:
                        title = await title_el.inner_text()
                        url = await url_el.inner_text()
                        snippet = await snippet_el.inner_text()
                        results.append(
                            f"Result {i+1}: {title}\nURL: {url.strip()}\nSnippet: {snippet.strip()}\n---"
                        )
                return "\n".join(results) if results else "No results found."
            finally:
                await browser.close()
    except Exception as e:
        return f"Browser search failed: {str(e)}"
