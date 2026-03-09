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


@sync_to_async
def _comment_sync(item_type: str, item_id: str, text: str) -> str:
    item_type = item_type.upper()

    # 1. Strict UUID Validation
    try:
        val_uuid = uuid.UUID(str(item_id))
    except ValueError:
        return (
            f"Error: Invalid item_id '{item_id}'. You must provide the full, "
            f'exact UUID (e.g., 123e4567-e89b-12d3-a456-426614174000).'
        )

    kwargs = {'text': text, 'status_id': PFCCommentStatus.CREATED}

    # 2. Explicit Target Validation & Assignment
    if item_type == 'EPIC':
        if not PFCEpic.objects.filter(id=val_uuid).exists():
            return (
                f"Error: EPIC with ID '{val_uuid}' does not exist on the board."
            )
        kwargs['epic_id'] = str(val_uuid)

    elif item_type == 'STORY':
        if not PFCStory.objects.filter(id=val_uuid).exists():
            return (
                f"Error: STORY with ID '{val_uuid}' "
                f'does not exist on the board.'
            )
        kwargs['story_id'] = str(val_uuid)

    elif item_type == 'TASK':
        if not PFCTask.objects.filter(id=val_uuid).exists():
            return (
                f"Error: TASK with ID '{val_uuid}' does not exist on the board."
            )
        kwargs['task_id'] = str(val_uuid)

    else:
        return (
            f"Error: Invalid item_type '{item_type}'. "
            f'Must be exactly EPIC, STORY, or TASK.'
        )

    # 3. Clean Execution
    try:
        comment = PFCComment.objects.create(**kwargs)
        return (
            f'SUCCESS: Comment {comment.id} created on {item_type} {item_id}.'
        )

    except IntegrityError as e:
        return (
            f'Database Error: Constraint failed. '
            f'Ensure PFCCommentStatus fixtures are loaded. ({str(e)})'
        )
    except ValidationError as e:
        return f'Validation Error: {str(e)}'
    except Exception as e:
        return f'ERROR creating comment: {str(e)}'


async def mcp_comment_add(item_type: str, item_id: str, text: str) -> str:
    """MCP Tool: Adds a structured comment or question to a specific Agile ticket."""
    return await _comment_sync(item_type, item_id, text)
