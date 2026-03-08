import json

from asgiref.sync import sync_to_async

from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask
from prefrontal_cortex.serializers import (
    PFCEpicSerializer,
    PFCStorySerializer,
    PFCTaskSerializer,
)

MODEL_MAP = {
    'EPIC': (PFCEpic, PFCEpicSerializer),
    'STORY': (PFCStory, PFCStorySerializer),
    'TASK': (PFCTask, PFCTaskSerializer),
}


@sync_to_async
def _create_sync(item_type: str, parent_id: str, payload: dict) -> str:
    item_type = item_type.upper()
    if item_type not in MODEL_MAP:
        return f"Error: Invalid item_type '{item_type}'. Must be EPIC, STORY, or TASK."

    _, serializer_class = MODEL_MAP[item_type]

    # Map parent relationships
    if item_type == 'STORY' and parent_id:
        payload['epic'] = parent_id
    elif item_type == 'TASK' and parent_id:
        payload['story'] = parent_id

    serializer = serializer_class(data=payload)
    if serializer.is_valid():
        instance = serializer.save()
        return f'SUCCESS: Created {item_type} with ID {instance.id}'

    return f'VALIDATION ERROR: {json.dumps(serializer.errors)}'


async def mcp_ticket_create(
    item_type: str, payload: dict, parent_id: str = None
) -> str:
    """MCP Tool: Creates a new Agile ticket. Payload must be a JSON dictionary of fields."""
    return await _create_sync(item_type, parent_id, payload)
