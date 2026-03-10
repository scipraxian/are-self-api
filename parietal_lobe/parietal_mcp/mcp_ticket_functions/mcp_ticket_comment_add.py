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
def _comment_sync(item_type: str, item_id: str, text: str) -> str:
    item_type_normalized = str(item_type).upper()

    # 1. Strict UUID Validation
    try:
        val_uuid = uuid.UUID(str(item_id))
    except ValueError:
        return make_action_response(
            action=TicketAction.COMMENT,
            ok=False,
            item_type=item_type_normalized,
            error=(
                f"Invalid item_id '{item_id}'. You must provide the full, "
                'exact UUID (e.g., 123e4567-e89b-12d3-a456-426614174000).'
            ),
        )

    kwargs = {'text': text, 'status_id': PFCCommentStatus.CREATED}

    # 2. Explicit Target Validation & Assignment
    if item_type_normalized == 'EPIC':
        if not PFCEpic.objects.filter(id=val_uuid).exists():
            return make_action_response(
                action=TicketAction.COMMENT,
                ok=False,
                item_type=item_type_normalized,
                error=f"EPIC with ID '{val_uuid}' does not exist on the board.",
            )
        kwargs['epic_id'] = str(val_uuid)

    elif item_type_normalized == 'STORY':
        if not PFCStory.objects.filter(id=val_uuid).exists():
            return make_action_response(
                action=TicketAction.COMMENT,
                ok=False,
                item_type=item_type_normalized,
                error=(
                    f"STORY with ID '{val_uuid}' "
                    'does not exist on the board.'
                ),
            )
        kwargs['story_id'] = str(val_uuid)

    elif item_type_normalized == 'TASK':
        if not PFCTask.objects.filter(id=val_uuid).exists():
            return make_action_response(
                action=TicketAction.COMMENT,
                ok=False,
                item_type=item_type_normalized,
                error=f"TASK with ID '{val_uuid}' does not exist on the board.",
            )
        kwargs['task_id'] = str(val_uuid)

    else:
        return make_action_response(
            action=TicketAction.COMMENT,
            ok=False,
            item_type=item_type_normalized,
            error=(
                f"Invalid item_type '{item_type_normalized}'. "
                'Must be exactly EPIC, STORY, or TASK.'
            ),
        )

    # 3. Clean Execution
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


async def execute(item_type: str, item_id: str, text: str) -> str:
    """Implementation of adding a comment to a ticket."""
    return await _comment_sync(item_type, item_id, text)
