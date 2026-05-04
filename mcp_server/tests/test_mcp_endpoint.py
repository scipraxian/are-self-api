"""HTTP-transport contract for the /mcp endpoint.

Pins the behavior MCP clients (Claude Code, Claude Desktop, Cowork)
depend on at the Streamable HTTP transport layer:

- POST /mcp with a JSON-RPC `initialize` request returns 200 with the
  protocol handshake.
- GET /mcp returns 405 Method Not Allowed (we don't offer an SSE
  notification stream — clients fall back to POST-only). Returning 501
  here used to surface as `[ERROR] Not Implemented: /mcp` on Claude
  Code start.
- The same contract holds at /mcp/ since both routes are registered
  (APPEND_SLASH can't redirect POSTs without dropping the body).
"""

import json

from common.tests.common_test_case import CommonTestCase


class TestMCPEndpointTransport(CommonTestCase):
    """Assert /mcp speaks the Streamable HTTP transport correctly."""

    URLS = ('/mcp', '/mcp/')

    def test_get_returns_405_with_allow_header(self):
        """Assert GET on /mcp and /mcp/ is 405 Method Not Allowed."""
        for url in self.URLS:
            response = self.client.get(url)
            assert response.status_code == 405, (
                url, response.status_code,
            )
            allow = response.headers.get('Allow', '')
            assert 'POST' in allow, (url, allow)
            assert 'DELETE' in allow, (url, allow)

    def test_post_initialize_returns_handshake(self):
        """Assert POST initialize returns 200 with serverInfo."""
        body = {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': {},
        }
        for url in self.URLS:
            response = self.client.post(
                url,
                data=json.dumps(body),
                content_type='application/json',
            )
            assert response.status_code == 200, (
                url, response.status_code, response.content,
            )
            payload = response.json()
            assert payload['jsonrpc'] == '2.0', payload
            assert payload['id'] == 1, payload
            result = payload['result']
            assert result['serverInfo']['name'] == 'are-self', result
            assert 'tools' in result['capabilities'], result
            # Mcp-Session-Id MUST be present per the transport spec.
            assert response.headers.get('Mcp-Session-Id'), response.headers

    def test_unsupported_method_returns_405(self):
        """Assert PATCH (unmapped verb) is 405."""
        for url in self.URLS:
            response = self.client.patch(
                url, data='{}', content_type='application/json',
            )
            assert response.status_code == 405, (
                url, response.status_code,
            )
