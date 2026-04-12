"""
Prefrontal Cortex (PFC) Tools
=============================

MCP tools for task management — listing and creating tasks within
Are-Self's Epic → Story → Task hierarchy.
"""

import logging
from typing import Any, Dict, List, Optional

from asgiref.sync import sync_to_async

from mcp_server.server import MCPToolRegistry

logger = logging.getLogger(__name__)


def register_pfc_tools(registry: MCPToolRegistry) -> None:
    """Register prefrontal cortex tools on the MCP registry."""

    # ----------------------------------------------------------
    # list_pfc_tasks
    # ----------------------------------------------------------

    async def list_pfc_tasks(
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List tasks from the prefrontal cortex."""
        from prefrontal_cortex.models import PFCTask

        @sync_to_async
        def _query():
            qs = PFCTask.objects.select_related(
                'status', 'story', 'story__epic'
            )
            if status:
                qs = qs.filter(status__name=status)
            rows = qs.values(
                'id',
                'name',
                'description',
                'status__name',
                'story__name',
                'story__epic__name',
            )[:limit]
            return list(rows)

        rows = await _query()
        return [
            {
                'id': str(r['id']),
                'name': r['name'],
                'description': r['description'],
                'status': r['status__name'],
                'story_name': r['story__name'],
                'epic_name': r['story__epic__name'],
            }
            for r in rows
        ]

    registry.register(
        name='list_pfc_tasks',
        description=(
            'List tasks from the prefrontal cortex. Tasks are '
            'tactical execution units within the Epic → Story → '
            'Task hierarchy.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'status': {
                    'type': 'string',
                    'description': (
                        'Filter by status name (e.g. '
                        '"SELECTED_FOR_DEVELOPMENT")'
                    ),
                },
                'limit': {
                    'type': 'integer',
                    'description': 'Max results (default 20)',
                    'default': 20,
                },
            },
        },
        handler=list_pfc_tasks,
    )

    # ----------------------------------------------------------
    # create_pfc_task
    # ----------------------------------------------------------

    async def create_pfc_task(
        name: str,
        story_id: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new task in the prefrontal cortex."""
        from prefrontal_cortex.models import (
            PFCItemStatus,
            PFCStory,
            PFCTask,
        )

        @sync_to_async
        def _create():
            story = PFCStory.objects.get(id=story_id)
            default_status = PFCItemStatus.objects.get(
                id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT
            )
            task = PFCTask.objects.create(
                name=name,
                description=description or '',
                story=story,
                status=default_status,
            )
            return {
                'id': str(task.id),
                'name': task.name,
                'message': 'Task created.',
            }

        try:
            result = await _create()
            logger.info(
                '[MCP] PFC task created: %s', result['id'][:8]
            )
            return result
        except Exception as e:
            logger.error(
                '[MCP] Failed to create PFC task: %s', str(e)
            )
            return {'error': 'Create failed: %s' % str(e)}

    registry.register(
        name='create_pfc_task',
        description=(
            'Create a new task in the prefrontal cortex, '
            'assigned to a parent story.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'name': {
                    'type': 'string',
                    'description': 'Task title',
                },
                'story_id': {
                    'type': 'string',
                    'description': 'UUID of the parent story',
                },
                'description': {
                    'type': 'string',
                    'description': 'Detailed task description',
                },
            },
            'required': ['name', 'story_id'],
        },
        handler=create_pfc_task,
    )

    logger.info('[MCP] PFC tools registered (2 tools).')
