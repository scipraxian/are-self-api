"""
Environment Tools
=================

MCP tools for discovering project environments and their context.
"""

import logging
from typing import Any, Dict, List

from asgiref.sync import sync_to_async

from mcp_server.server import MCPToolRegistry

logger = logging.getLogger(__name__)


def register_environment_tools(registry: MCPToolRegistry) -> None:
    """Register environment tools on the MCP tool registry."""

    async def list_environments() -> List[Dict[str, Any]]:
        """List all available project environments."""
        from environments.models import ProjectEnvironment

        @sync_to_async
        def _query():
            return list(
                ProjectEnvironment.objects.select_related(
                    'type', 'status'
                ).values(
                    'id',
                    'name',
                    'description',
                    'available',
                    'type__name',
                    'status__name',
                )
            )

        rows = await _query()
        return [
            {
                'id': str(r['id']),
                'name': r['name'],
                'description': r['description'],
                'is_active': r['available'],
                'type': r['type__name'],
                'status': r['status__name'],
            }
            for r in rows
        ]

    registry.register(
        name='list_environments',
        description=(
            'List all available project environments. Each '
            'environment provides execution context including '
            'type, status, and context variables.'
        ),
        input_schema={
            'type': 'object',
            'properties': {},
        },
        handler=list_environments,
    )

    logger.info('[MCP] Environment tools registered (1 tool).')
