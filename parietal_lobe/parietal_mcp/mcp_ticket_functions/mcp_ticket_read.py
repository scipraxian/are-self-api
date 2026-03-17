import uuid

from asgiref.sync import sync_to_async

from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask
from prefrontal_cortex.serializers import (
    PFCEpicSerializer,
    PFCStorySerializer,
    PFCTaskSerializer,
    TicketAction,
    make_action_response,
)


MODEL_SERIALIZER_SEQ = [
    ('EPIC', PFCEpic, PFCEpicSerializer),
    ('STORY', PFCStory, PFCStorySerializer),
    ('TASK', PFCTask, PFCTaskSerializer),
]


@sync_to_async
def _read_sync(item_id: str) -> str:
    """
    Lookup a ticket by UUID across EPIC, STORY, and TASK.

    Returns a JSON string with a consistent shape so the caller
    can parse it reliably.
    """
    try:
        val_uuid = uuid.UUID(str(item_id))
    except ValueError:
        return make_action_response(
            action=TicketAction.READ,
            ok=False,
            error=(
                f"Invalid item_id '{item_id}'. You must provide the full, "
                'exact UUID (e.g., 123e4567-e89b-12d3-a456-426614174000).'
            ),
        )

    for type_name, model_cls, serializer_cls in MODEL_SERIALIZER_SEQ:
        try:
            instance = model_cls.objects.get(id=val_uuid)
        except model_cls.DoesNotExist:
            continue

        item_serializer = serializer_cls(instance)
        return make_action_response(
            action=TicketAction.READ,
            item_type=type_name,
            item_id=val_uuid,
            data=item_serializer.data,
        )

    return make_action_response(
        action=TicketAction.READ,
        ok=False,
        error=f"No ticket with ID '{val_uuid}' found.",
    )


async def execute(item_type: str, item_id: str, **kwargs) -> str:
    """
    Implementation of ticket read.

    item_id alone is sufficient; the type is inferred from the UUID.
    """
    _ = item_type, kwargs  # backwards-compat shim for any legacy callers
    return await _read_sync(item_id=item_id)
