from urllib.parse import quote_plus

import requests


def mcp_internet_query(query: str, thought: str = '') -> str:
    """MCP Tool: Search the web using DuckDuckGo (lightweight, no browser)."""
    try:
        url = f'https://html.duckduckgo.com/html/?q={quote_plus(query)}'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 Chrome/125.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self._current = {}
                self._capture = None

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                cls = attrs_dict.get('class', '')

                if 'result__title' in cls:
                    self._capture = 'title'
                    self._current = {}
                elif 'result__url' in cls:
                    self._capture = 'url'
                elif 'result__snippet' in cls:
                    self._capture = 'snippet'

            def handle_data(self, data):
                if self._capture:
                    self._current[self._capture] = (
                        self._current.get(self._capture, '') + data
                    )

            def handle_endtag(self, tag):
                if tag in ('a', 'span', 'td') and self._capture:
                    if self._capture == 'snippet':
                        self._current['snippet'] = self._current.get(
                            'snippet', ''
                        ).strip()
                        if self._current.get('title') and self._current.get(
                            'url'
                        ):
                            self.results.append(self._current)
                            self._current = {}
                    self._capture = None

        parser = DDGParser()
        parser.feed(resp.text)

        if not parser.results:
            return 'No results found.'

        lines = []
        for i, r in enumerate(parser.results[:5]):
            lines.append(
                f'Result {i + 1}: {r.get("title", "N/A")}\n'
                f'URL: {r.get("url", "N/A")}\n'
                f'Snippet: {r.get("snippet", "N/A")}\n'
                f'---'
            )
        return '\n'.join(lines)

    except Exception as e:
        return f'Browser search failed: {str(e)}'
