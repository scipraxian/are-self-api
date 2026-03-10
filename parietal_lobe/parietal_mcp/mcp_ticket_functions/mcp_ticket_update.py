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
def _update_sync(item_id: str, payload: dict) -> str:
    """
    UUID-only update: infer ticket type by walking the models until one matches.
    """
    try:
        val_uuid = uuid.UUID(str(item_id))
    except ValueError:
        return make_action_response(
            action=TicketAction.UPDATE,
            ok=False,
            error=(
                "Invalid item_id "
                f"'{item_id}'. You must provide the full, exact UUID "
                '(e.g., 123e4567-e89b-12d3-a456-426614174000).'
            ),
        )

    for type_name, model_class, serializer_class in MODEL_SERIALIZER_SEQ:
        try:
            instance = model_class.objects.get(id=val_uuid)
        except model_class.DoesNotExist:
            continue

        serializer = serializer_class(instance, data=payload, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return make_action_response(
                action=TicketAction.UPDATE,
                item_type=type_name,
                item_id=val_uuid,
                data=serializer.data,
            )

        return make_action_response(
            action=TicketAction.UPDATE,
            ok=False,
            item_type=type_name,
            item_id=val_uuid,
            error=f'VALIDATION ERROR: {serializer.errors}',
        )

    return make_action_response(
        action=TicketAction.UPDATE,
        ok=False,
        error=f"No ticket with ID '{val_uuid}' found.",
    )


async def execute(item_type: str, item_id: str, payload: dict) -> str:
    """
    Implementation of ticket updates.

    The router currently supplies item_type, but we ignore it here and
    infer the type from the UUID instead.
    """
    # Silence unused-arg linters while documenting intent
    _ = item_type
    return await _update_sync(item_id=item_id, payload=payload)

