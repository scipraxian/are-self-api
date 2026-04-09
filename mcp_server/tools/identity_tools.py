"""
Identity Tools
==============

MCP tools for discovering deployed identity instances (IdentityDiscs).
"""

import logging
from typing import Any, Dict, List

from asgiref.sync import sync_to_async

from mcp_server.server import MCPToolRegistry

logger = logging.getLogger(__name__)


def register_identity_tools(registry: MCPToolRegistry) -> None:
    """Register identity tools on the MCP tool registry."""

    async def list_identity_discs() -> List[Dict[str, Any]]:
        """List all deployed identity discs."""
        from identity.models import IdentityDisc

        @sync_to_async
        def _query():
            return list(
                IdentityDisc.objects.select_related(
                    'identity_type'
                ).values(
                    'id',
                    'name',
                    'identity_type__name',
                    'available',
                )
            )

        rows = await _query()
        return [
            {
                'id': str(r['id']),
                'name': r['name'],
                'identity_name': (
                    r['identity_type__name'] or 'Unknown'
                ),
                'is_active': r['available'],
            }
            for r in rows
        ]

    registry.register(
        name='list_identity_discs',
        description=(
            'List all deployed identity instances (IdentityDiscs). '
            'Each disc is a running instance of an identity '
            'blueprint with its own state and budget tracking.'
        ),
        input_schema={
            'type': 'object',
            'properties': {},
        },
        handler=list_identity_discs,
    )

    logger.info('[MCP] Identity tools registered (1 tool).')
