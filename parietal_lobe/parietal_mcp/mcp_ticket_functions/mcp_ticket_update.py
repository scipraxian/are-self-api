import uuid

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError

from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory, PFCTask
from prefrontal_cortex.serializers import (
    TicketAction,
    make_action_response,
)

from .constants import EPIC, STATUS_ID, STATUS_KEY, STORY, TASK

MODEL_SEQ = [
    (EPIC, PFCEpic),
    (STORY, PFCStory),
    (TASK, PFCTask),
]


def _auto_status_update(instance, type_name: str):
    """
    Bubbles up status changes to parent tickets after a successful MCP update.
    """
    current_status_id = instance.status_id

    if type_name == TASK:
        story = instance.story
        # 1. Bubbling UP 'IN_PROGRESS'
        if (
            current_status_id == PFCItemStatus.IN_PROGRESS
            and story.status_id == PFCItemStatus.SELECTED_FOR_DEVELOPMENT
        ):
            story.status_id = PFCItemStatus.IN_PROGRESS
            story.save(update_fields=[STATUS_KEY])

        # 2. Bubbling UP 'DONE' -> 'IN_REVIEW'
        elif current_status_id == PFCItemStatus.DONE:
            # GUARD: Only bubble up if the story hasn't already advanced past IN_PROGRESS
            if story.status_id in [
                PFCItemStatus.SELECTED_FOR_DEVELOPMENT,
                PFCItemStatus.IN_PROGRESS,
            ]:
                pending = story.tasks.exclude(
                    status_id=PFCItemStatus.DONE
                ).exists()
                if not pending:
                    story.status_id = PFCItemStatus.IN_REVIEW
                    story.save(update_fields=[STATUS_KEY])

    elif type_name == STORY:
        epic = instance.epic
        # 1. Bubbling UP 'IN_PROGRESS'
        if (
            current_status_id == PFCItemStatus.IN_PROGRESS
            and epic.status_id == PFCItemStatus.SELECTED_FOR_DEVELOPMENT
        ):
            epic.status_id = PFCItemStatus.IN_PROGRESS
            epic.save(update_fields=[STATUS_KEY])

        # 2. Bubbling UP 'DONE' -> 'BLOCKED_BY_USER'
        elif current_status_id == PFCItemStatus.DONE:
            # GUARD: Only bubble up if the epic hasn't already advanced past IN_PROGRESS
            if epic.status_id in [
                PFCItemStatus.SELECTED_FOR_DEVELOPMENT,
                PFCItemStatus.IN_PROGRESS,
            ]:
                pending = epic.stories.exclude(
                    status_id=PFCItemStatus.DONE
                ).exists()
                if not pending:
                    epic.status_id = PFCItemStatus.BLOCKED_BY_USER
                    epic.save(update_fields=[STATUS_KEY])


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
                'Invalid item_id '
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

    for type_name, model_class in MODEL_SEQ:
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
        if field_name in [STATUS_KEY, STATUS_ID] and str(field_value) == str(
            PFCItemStatus.BACKLOG
        ):
            if type_name == STORY:
                if not instance.perspective or not instance.assertions:
                    return make_action_response(
                        action=TicketAction.UPDATE,
                        ok=False,
                        item_type=type_name,
                        item_id=val_uuid,
                        error="SYSTEM REJECTION: Definition of Ready (DoR) is not met. You MUST populate 'perspective' and 'assertions' before moving this Story to BACKLOG.",
                    )
        try:
            setattr(instance, field_name, field_value)
        except ValueError as e:
            # Try id lookup.
            fk_field_name = f'{field_name}_id'
            if hasattr(instance, fk_field_name):
                setattr(instance, fk_field_name, field_value)
            else:
                return make_action_response(
                    action=TicketAction.UPDATE,
                    ok=False,
                    item_type=type_name,
                    item_id=val_uuid,
                    error=f"Invalid value for '{field_name}': {str(e)}",
                )

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

        _auto_status_update(instance, type_name)
        return make_action_response(
            action=TicketAction.UPDATE,
            item_type=type_name,
            item_id=val_uuid,
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
