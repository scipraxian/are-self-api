"""
Thalamus Tools
==============

MCP tools for sending messages through the thalamus chat relay.
Currently logs and acknowledges; full Thalamus delivery with
WebSocket neurotransmitters is not yet wired.
"""

import logging
from typing import Any, Dict, Optional

from mcp_server.server import MCPToolRegistry

logger = logging.getLogger(__name__)


def register_thalamus_tools(registry: MCPToolRegistry) -> None:
    """Register thalamus tools on the MCP tool registry."""

    async def send_thalamus_message(
        message: str,
        identity_disc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a message through the chat relay."""
        logger.info(
            '[MCP] Thalamus message (disc=%s): %s',
            identity_disc_id or 'none',
            message[:100],
        )
        # Log-only for now; future: create ThalamusMessage and fire neurotransmitter.
        return {
            'message': 'Message sent.',
            'delivered': True,
            'identity_disc_id': identity_disc_id,
        }

    registry.register(
        name='send_thalamus_message',
        description=(
            'Send a message through the thalamus chat relay. '
            'Currently logs only; WebSocket delivery is not yet implemented.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'message': {
                    'type': 'string',
                    'description': 'Message content to send',
                },
                'identity_disc_id': {
                    'type': 'string',
                    'description': (
                        'Optional identity disc UUID sending '
                        'the message'
                    ),
                },
            },
            'required': ['message'],
        },
        handler=send_thalamus_message,
    )

    logger.info('[MCP] Thalamus tools registered (1 tool).')
