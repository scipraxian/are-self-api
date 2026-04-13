"""
Django ASGI Bridge for MCP
==========================

A Django async view that implements the MCP Streamable HTTP transport
protocol. Handles JSON-RPC 2.0 request routing, session management,
and tool dispatch.

Endpoint: /mcp (mounted in config/urls.py)

Supports:
- POST: JSON-RPC 2.0 requests (initialize, tools/list, tools/call)
- GET:  SSE stream for server notifications (not yet implemented)
- DELETE: Session termination
"""

import json
import logging
import uuid

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from mcp_server.server import MCPToolRegistry, create_mcp_server

logger = logging.getLogger(__name__)

# Protocol constants
PROTOCOL_VERSION = '2024-11-05'
SERVER_NAME = 'are-self'
SERVER_VERSION = '1.0.0'

# Module-level singleton (created on first request)
_registry: MCPToolRegistry = None


def _get_registry() -> MCPToolRegistry:
    """Lazy-initialize the MCP tool registry."""
    global _registry
    if _registry is None:
        _registry = create_mcp_server()
    return _registry


@csrf_exempt
async def mcp_endpoint(request):
    """
    Main MCP endpoint.

    Implements the Streamable HTTP transport for the Model Context
    Protocol. All JSON-RPC 2.0 messages flow through this single
    endpoint.
    """
    if request.method == 'POST':
        return await _handle_post(request)
    elif request.method == 'GET':
        return _handle_get_sse(request)
    elif request.method == 'DELETE':
        return _handle_delete(request)
    else:
        return JsonResponse(
            {'error': 'Method not allowed'}, status=405
        )


async def _handle_post(request) -> JsonResponse:
    """Process a JSON-RPC 2.0 POST request."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {
                'jsonrpc': '2.0',
                'error': {'code': -32700, 'message': 'Parse error'},
                'id': None,
            },
            status=400,
        )

    session_id = request.headers.get('Mcp-Session-Id', '')
    if not session_id:
        session_id = str(uuid.uuid4())

    method = body.get('method', '')
    request_id = body.get('id')
    params = body.get('params', {})

    logger.info('[MCP] %s (session=%s)', method, session_id[:8])

    try:
        result = await _dispatch(method, params)

        # Notifications have no id and expect no response body
        if request_id is None:
            response = HttpResponse(status=202)
            response['Mcp-Session-Id'] = session_id
            return response

        response = JsonResponse(
            {
                'jsonrpc': '2.0',
                'result': result,
                'id': request_id,
            }
        )
        response['Mcp-Session-Id'] = session_id
        return response

    except Exception as e:
        logger.exception('[MCP] Error dispatching %s', method)
        return JsonResponse(
            {
                'jsonrpc': '2.0',
                'error': {
                    'code': -32603,
                    'message': str(e),
                },
                'id': request_id,
            },
            status=500,
        )


async def _dispatch(method: str, params: dict) -> dict:
    """Route a JSON-RPC method to the appropriate handler."""
    registry = _get_registry()

    if method == 'initialize':
        return {
            'protocolVersion': PROTOCOL_VERSION,
            'capabilities': {
                'tools': {'listChanged': False},
            },
            'serverInfo': {
                'name': SERVER_NAME,
                'version': SERVER_VERSION,
            },
        }

    elif method == 'notifications/initialized':
        return {}

    elif method == 'tools/list':
        return {'tools': registry.list_tools()}

    elif method == 'tools/call':
        tool_name = params.get('name', '')
        arguments = params.get('arguments', {})
        return await registry.call_tool(tool_name, arguments)

    elif method == 'ping':
        return {}

    else:
        raise ValueError('Method not found: %s' % method)


def _handle_get_sse(request) -> HttpResponse:
    """SSE stream for server-initiated notifications (stub)."""
    return JsonResponse(
        {'message': 'SSE notifications — not yet implemented'},
        status=501,
    )


def _handle_delete(request) -> HttpResponse:
    """Session termination."""
    session_id = request.headers.get('Mcp-Session-Id', '')
    logger.info('[MCP] Session %s terminated.', session_id[:8])
    return HttpResponse(status=204)
