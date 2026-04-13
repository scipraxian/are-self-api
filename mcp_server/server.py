"""
MCP Server for Are-Self
=======================

A lightweight MCP-compliant tool registry and dispatcher integrated into
Django's ASGI stack. Speaks JSON-RPC 2.0 over Streamable HTTP at /mcp.

Rather than using FastMCP's built-in HTTP server (which conflicts with
Daphne/Channels), this module implements a thin registry that stores tool
schemas and async handlers, then dispatches via a Django async view.

Current scope: request/response tools (list, launch, read, write).
Planned: streaming via neurotransmitter callbacks (SSE notifications).
"""

import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# Type alias for async tool handlers
ToolHandler = Callable[..., Coroutine[Any, Any, Any]]


class MCPToolRegistry:
    """
    Stores tool schemas and their async handler functions.

    Each tool has:
    - A JSON Schema definition (name, description, inputSchema)
    - An async handler that executes the tool logic
    """

    def __init__(self) -> None:
        self._tools: List[Dict[str, Any]] = []
        self._handlers: Dict[str, ToolHandler] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: ToolHandler,
    ) -> None:
        """Register a single tool with its schema and handler."""
        self._tools.append(
            {
                'name': name,
                'description': description,
                'inputSchema': input_schema,
            }
        )
        self._handlers[name] = handler
        logger.debug('[MCP] Registered tool: %s', name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return all registered tool schemas."""
        return self._tools

    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Dispatch a tool call to its handler."""
        handler = self._handlers.get(name)
        if not handler:
            return {
                'content': [
                    {
                        'type': 'text',
                        'text': 'Error: Unknown tool "%s"' % name,
                    }
                ],
                'isError': True,
            }

        try:
            result = await handler(**arguments)
            text = json.dumps(result, default=str)
            return {
                'content': [{'type': 'text', 'text': text}],
                'isError': False,
            }
        except Exception as e:
            logger.exception('[MCP] Tool "%s" failed', name)
            return {
                'content': [
                    {
                        'type': 'text',
                        'text': 'Tool execution error: %s' % str(e),
                    }
                ],
                'isError': True,
            }

    @property
    def tool_count(self) -> int:
        """Number of registered tools."""
        return len(self._tools)


def create_mcp_server() -> MCPToolRegistry:
    """Factory that builds the configured MCP tool registry."""
    registry = MCPToolRegistry()

    from mcp_server.tools.cns_tools import register_cns_tools
    from mcp_server.tools.environment_tools import (
        register_environment_tools,
    )
    from mcp_server.tools.hippocampus_tools import (
        register_hippocampus_tools,
    )
    from mcp_server.tools.identity_tools import register_identity_tools
    from mcp_server.tools.pfc_tools import register_pfc_tools
    from mcp_server.tools.thalamus_tools import register_thalamus_tools

    register_cns_tools(registry)
    register_identity_tools(registry)
    register_environment_tools(registry)
    register_hippocampus_tools(registry)
    register_pfc_tools(registry)
    register_thalamus_tools(registry)

    logger.info(
        '[MCP] Are-Self MCP Server initialized (%d tools).',
        registry.tool_count,
    )
    return registry
