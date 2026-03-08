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
def _update_sync(item_type: str, item_id: str, payload: dict) -> str:
    item_type = item_type.upper()
    if item_type not in MODEL_MAP:
        return f"Error: Invalid item_type '{item_type}'."

    model_class, serializer_class = MODEL_MAP[item_type]

    try:
        instance = model_class.objects.get(id=item_id)
    except model_class.DoesNotExist:
        return f'Error: {item_type} with ID {item_id} not found.'

    # partial=True allows us to update only the fields the LLM provides
    serializer = serializer_class(instance, data=payload, partial=True)
    if serializer.is_valid():
        serializer.save()
        return f'SUCCESS: Updated {item_type} {item_id}.'

    return f'VALIDATION ERROR: {json.dumps(serializer.errors)}'


async def mcp_ticket_update(item_type: str, item_id: str, payload: dict) -> str:
    """MCP Tool: Updates an existing Agile ticket. Payload must be a JSON dictionary of fields to change."""
    return await _update_sync(item_type, item_id, payload)
