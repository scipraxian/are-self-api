import logging
import uuid

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


@sync_to_async
def _update_bb_sync(spike_id: str, key: str, value: str) -> str:
    from central_nervous_system.models import Spike
    try:
        val_uuid = uuid.UUID(str(spike_id))
    except ValueError:
        return f"Error: Invalid Spike ID '{spike_id}'. Must be a UUID."

    try:
        spike = Spike.objects.get(id=val_uuid)
        if not isinstance(spike.blackboard, dict):
            spike.blackboard = {}

        spike.blackboard[key] = value
        spike.save(update_fields=['blackboard'])
        logger.info(
            f"[Parietal] Blackboard mutated for Spike {spike_id}: {key}={value}")
        return f"Success: Blackboard updated. {key} is now '{value}'."
    except Spike.DoesNotExist:
        return f"Error: Spike {spike_id} not found."
    except Exception as e:
        logger.error(f"[Parietal] Blackboard update failed: {e}")
        return f"Error updating blackboard: {str(e)}"


async def mcp_update_blackboard(
    spike_id: str, key: str, value: str, thought: str = ''
) -> str:
    """MCP Tool: Updates a value in the Spike blackboard."""
    return await _update_bb_sync(spike_id, key, value)
