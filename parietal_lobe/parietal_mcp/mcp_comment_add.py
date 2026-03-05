from asgiref.sync import sync_to_async

from prefrontal_cortex.models import PFCComment, PFCCommentStatus


@sync_to_async
def _comment_sync(item_type: str, item_id: str, text: str) -> str:
    item_type = item_type.upper()
    kwargs = {'text': text, 'status_id': PFCCommentStatus.CREATED}

    if item_type == 'EPIC':
        kwargs['epic_id'] = item_id
    elif item_type == 'STORY':
        kwargs['story_id'] = item_id
    elif item_type == 'TASK':
        kwargs['task_id'] = item_id
    else:
        return f"Error: Invalid item_type '{item_type}'."

    try:
        comment = PFCComment.objects.create(**kwargs)
        return (
            f'SUCCESS: Comment {comment.id} created on {item_type} {item_id}.'
        )
    except Exception as e:
        return f'ERROR creating comment: {str(e)}'


async def mcp_comment_add(item_type: str, item_id: str, text: str) -> str:
    """MCP Tool: Adds a structured comment or question to a specific Agile ticket."""
    return await _comment_sync(item_type, item_id, text)
