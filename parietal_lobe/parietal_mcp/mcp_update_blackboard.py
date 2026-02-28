import logging
import uuid

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


@sync_to_async
def _update_bb_sync(head_id: str, key: str, value: str) -> str:
    from central_nervous_system.models import CNSHead
    try:
        val_uuid = uuid.UUID(str(head_id))
    except ValueError:
        return f"Error: Invalid Head ID '{head_id}'. Must be a UUID."

    try:
        head = CNSHead.objects.get(id=val_uuid)
        if not isinstance(head.blackboard, dict):
            head.blackboard = {}

        head.blackboard[key] = value
        head.save(update_fields=['blackboard'])
        logger.info(
            f"[Parietal] Blackboard mutated for Head {head_id}: {key}={value}")
        return f"Success: Blackboard updated. {key} is now '{value}'."
    except CNSHead.DoesNotExist:
        return f"Error: CNSHead {head_id} not found."
    except Exception as e:
        logger.error(f"[Parietal] Blackboard update failed: {e}")
        return f"Error updating blackboard: {str(e)}"


async def mcp_update_blackboard(head_id: str, key: str, value: str) -> str:
    """MCP Tool: Updates a value in the CNSHead blackboard."""
    return await _update_bb_sync(head_id, key, value)
