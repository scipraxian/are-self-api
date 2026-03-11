import uuid

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError

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
def _update_sync(item_id: str, field_name: str, field_value: str) -> str:
    """
    UUID-only, single-field update: infer ticket type by walking the models
    until one matches, then setattr(field_name, field_value), validate, save.
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

    if not (field_name or '').strip():
        return make_action_response(
            action=TicketAction.UPDATE,
            ok=False,
            error='field_name is required for update.',
        )

    for type_name, model_class, serializer_class in MODEL_SERIALIZER_SEQ:
        try:
            instance = model_class.objects.get(id=val_uuid)
        except model_class.DoesNotExist:
            continue

        if not hasattr(instance, field_name):
            return make_action_response(
                action=TicketAction.UPDATE,
                ok=False,
                item_type=type_name,
                item_id=val_uuid,
                error=f"Field '{field_name}' does not exist on {type_name}.",
            )

        # Apply the atomic field update
        setattr(instance, field_name, field_value)
        try:
            instance.full_clean()
            instance.save()
        except ValidationError as e:
            return make_action_response(
                action=TicketAction.UPDATE,
                ok=False,
                item_type=type_name,
                item_id=val_uuid,
                error=f'VALIDATION ERROR: {e.messages}',
            )

        serializer = serializer_class(instance)
        return make_action_response(
            action=TicketAction.UPDATE,
            item_type=type_name,
            item_id=val_uuid,
            data=serializer.data,
        )

    return make_action_response(
        action=TicketAction.UPDATE,
        ok=False,
        error=f"No ticket with ID '{val_uuid}' found.",
    )


async def execute(
    item_id: str | None = None,
    field_name: str | None = None,
    field_value: str | None = None,
    **_: object,
) -> str:
    """
    Implementation of ticket updates using a flat, single-field model.
    """
    return await _update_sync(
        item_id=str(item_id or ''),
        field_name=str(field_name or ''),
        field_value=str(field_value or ''),
    )

