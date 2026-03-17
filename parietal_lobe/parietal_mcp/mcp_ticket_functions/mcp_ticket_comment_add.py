import uuid

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from prefrontal_cortex.models import (
    PFCComment,
    PFCCommentStatus,
    PFCEpic,
    PFCStory,
    PFCTask,
)
from prefrontal_cortex.serializers import TicketAction, make_action_response


@sync_to_async
def _comment_sync(item_id: str, text: str) -> str:
    """
    Add a comment to a ticket by inferring its type from the UUID alone.
    """
    try:
        val_uuid = uuid.UUID(str(item_id))
    except ValueError:
        return make_action_response(
            action=TicketAction.COMMENT,
            ok=False,
            error=(
                f"Invalid item_id '{item_id}'. You must provide the full, "
                'exact UUID (e.g., 123e4567-e89b-12d3-a456-426614174000).'
            ),
        )

    kwargs = {'text': text, 'status_id': PFCCommentStatus.CREATED}

    item_type_normalized = ''

    if PFCEpic.objects.filter(id=val_uuid).exists():
        item_type_normalized = 'EPIC'
        kwargs['epic_id'] = str(val_uuid)
    elif PFCStory.objects.filter(id=val_uuid).exists():
        item_type_normalized = 'STORY'
        kwargs['story_id'] = str(val_uuid)
    elif PFCTask.objects.filter(id=val_uuid).exists():
        item_type_normalized = 'TASK'
        kwargs['task_id'] = str(val_uuid)
    else:
        return make_action_response(
            action=TicketAction.COMMENT,
            ok=False,
            error=f"No EPIC/STORY/TASK with ID '{val_uuid}' exists on the board.",
        )

    try:
        comment = PFCComment.objects.create(**kwargs)
        return make_action_response(
            action=TicketAction.COMMENT,
            item_type=item_type_normalized,
            item_id=val_uuid,
            data={'comment_id': str(comment.id)},
        )

    except IntegrityError as e:
        return make_action_response(
            action=TicketAction.COMMENT,
            ok=False,
            item_type=item_type_normalized,
            error=(
                'Database Error: Constraint failed. '
                f'Ensure PFCCommentStatus fixtures are loaded. ({str(e)})'
            ),
        )
    except ValidationError as e:
        return make_action_response(
            action=TicketAction.COMMENT,
            ok=False,
            item_type=item_type_normalized,
            error=f'Validation Error: {str(e)}',
        )
    except Exception as e:  # pragma: no cover - defensive
        return make_action_response(
            action=TicketAction.COMMENT,
            ok=False,
            item_type=item_type_normalized,
            error=f'ERROR creating comment: {str(e)}',
        )


async def execute(
    item_id: str | None = None,
    field_value: str | None = None,
    **_: object,
) -> str:
    """Implementation of adding a comment to a ticket using flat arguments."""
    return await _comment_sync(item_id=str(item_id or ''), text=str(field_value or ''))
