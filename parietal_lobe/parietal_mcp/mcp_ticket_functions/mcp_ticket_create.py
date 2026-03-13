from asgiref.sync import sync_to_async

from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask
from prefrontal_cortex.serializers import (
    PFCEpicSerializer,
    PFCStorySerializer,
    PFCTaskSerializer,
    TicketAction,
    make_action_response,
)


MODEL_MAP = {
    'EPIC': (PFCEpic, PFCEpicSerializer),
    'STORY': (PFCStory, PFCStorySerializer),
    'TASK': (PFCTask, PFCTaskSerializer),
}


@sync_to_async
def _create_sync(item_type: str, payload: dict, parent_id: str | None = None) -> str:
    item_type_normalized = str(item_type).upper()
    if item_type_normalized not in MODEL_MAP:
        return make_action_response(
            action=TicketAction.CREATE,
            ok=False,
            item_type=item_type_normalized,
            error=(
                f"Invalid item_type '{item_type_normalized}'. "
                'Must be EPIC, STORY, or TASK.'
            ),
        )

    _, serializer_class = MODEL_MAP[item_type_normalized]

    # Map parent relationships
    payload = dict(payload or {})
    if item_type_normalized == 'STORY' and parent_id:
        payload['epic'] = parent_id
    elif item_type_normalized == 'TASK' and parent_id:
        payload['story'] = parent_id

    serializer = serializer_class(data=payload)
    if serializer.is_valid():
        instance = serializer.save()
        return make_action_response(
            action=TicketAction.CREATE,
            item_type=item_type_normalized,
            item_id=instance.id,
            data=serializer.data,
        )

    return make_action_response(
        action=TicketAction.CREATE,
        ok=False,
        item_type=item_type_normalized,
        error=f'VALIDATION ERROR: {serializer.errors}',
    )


async def execute(item_type: str, payload: dict, parent_id: str | None = None) -> str:
    """Implementation of ticket creation."""
    return await _create_sync(item_type, payload, parent_id)
