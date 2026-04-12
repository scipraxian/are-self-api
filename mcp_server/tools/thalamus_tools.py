"""
Thalamus Tools
==============

MCP tools for sending messages through the thalamus chat relay.
Phase 1 logs and acknowledges. Phase 2 wires into the full
Thalamus message pipeline with WebSocket delivery.
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
        # Phase 1: Log-only. Phase 2 will create a
        # ThalamusMessage and fire a neurotransmitter.
        return {
            'message': 'Message sent.',
            'delivered': True,
            'identity_disc_id': identity_disc_id,
        }

    registry.register(
        name='send_thalamus_message',
        description=(
            'Send a message through the thalamus chat relay. '
            'Phase 1 logs the message. Phase 2 will deliver '
            'via WebSocket neurotransmitters.'
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
