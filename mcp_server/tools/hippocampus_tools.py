"""
Hippocampus Tools
=================

MCP tools for searching, reading, and creating engrams (memories)
in Are-Self's vector memory system.
"""

import logging
from typing import Any, Dict, List, Optional

from asgiref.sync import sync_to_async

from mcp_server.server import MCPToolRegistry

logger = logging.getLogger(__name__)


def register_hippocampus_tools(registry: MCPToolRegistry) -> None:
    """Register hippocampus (memory) tools on the MCP registry."""

    # ----------------------------------------------------------
    # search_engrams
    # ----------------------------------------------------------

    async def search_engrams(
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search Are-Self's memory store."""
        from hippocampus.models import Engram

        @sync_to_async
        def _query():
            qs = (
                Engram.objects.filter(
                    name__icontains=query, is_active=True
                )
                .prefetch_related('tags')
                .order_by('-modified')[:limit]
            )
            results = []
            for e in qs:
                tags = list(
                    e.tags.values_list('name', flat=True)
                )
                results.append(
                    {
                        'id': str(e.id),
                        'name': e.name,
                        'content': e.description or '',
                        'tags': tags,
                        'created': (
                            e.created.isoformat()
                            if e.created
                            else None
                        ),
                    }
                )
            return results

        return await _query()

    registry.register(
        name='search_engrams',
        description=(
            'Search Are-Self\'s memory store (hippocampus) for '
            'engrams matching a text query. Phase 2 will add '
            'vector similarity search.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'query': {
                    'type': 'string',
                    'description': 'Text to search engram names',
                },
                'limit': {
                    'type': 'integer',
                    'description': 'Max results (default 10)',
                    'default': 10,
                },
            },
            'required': ['query'],
        },
        handler=search_engrams,
    )

    # ----------------------------------------------------------
    # read_engram
    # ----------------------------------------------------------

    async def read_engram(
        engram_id: str,
    ) -> Dict[str, Any]:
        """Read a specific engram by ID."""
        from hippocampus.models import Engram

        @sync_to_async
        def _query():
            e = Engram.objects.prefetch_related('tags').get(
                id=engram_id
            )
            tags = list(
                e.tags.values_list('name', flat=True)
            )
            return {
                'id': str(e.id),
                'name': e.name,
                'content': e.description or '',
                'tags': tags,
                'created': (
                    e.created.isoformat()
                    if e.created
                    else None
                ),
                'modified': (
                    e.modified.isoformat()
                    if e.modified
                    else None
                ),
            }

        try:
            return await _query()
        except Exception:
            return {'error': 'Engram %s not found' % engram_id}

    registry.register(
        name='read_engram',
        description=(
            'Retrieve a specific engram (memory) by its ID, '
            'including full content and tags.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'engram_id': {
                    'type': 'string',
                    'description': 'UUID of the engram to read',
                },
            },
            'required': ['engram_id'],
        },
        handler=read_engram,
    )

    # ----------------------------------------------------------
    # save_engram
    # ----------------------------------------------------------

    async def save_engram(
        name: str,
        content: str,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a new engram in the hippocampus."""
        from hippocampus.models import Engram, EngramTag

        @sync_to_async
        def _create():
            engram = Engram.objects.create(
                name=name, description=content
            )
            if tags:
                for tag_name in tags:
                    tag, _ = EngramTag.objects.get_or_create(
                        name=tag_name
                    )
                    engram.tags.add(tag)
            return {
                'id': str(engram.id),
                'name': engram.name,
                'message': 'Engram saved.',
            }

        try:
            result = await _create()
            logger.info(
                '[MCP] Engram created: %s', result['id'][:8]
            )
            return result
        except Exception as e:
            logger.error(
                '[MCP] Failed to save engram: %s', str(e)
            )
            return {'error': 'Save failed: %s' % str(e)}

    registry.register(
        name='save_engram',
        description=(
            'Create a new engram (memory) in Are-Self\'s '
            'hippocampus with optional tags.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'name': {
                    'type': 'string',
                    'description': 'Short name for the memory',
                },
                'content': {
                    'type': 'string',
                    'description': 'Full content of the memory',
                },
                'tags': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Optional tags for categorizing',
                },
            },
            'required': ['name', 'content'],
        },
        handler=save_engram,
    )

    logger.info('[MCP] Hippocampus tools registered (3 tools).')
