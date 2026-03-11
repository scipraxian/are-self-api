import importlib
import logging
from enum import Enum

from prefrontal_cortex.serializers import TicketAction

logger = logging.getLogger(__name__)

MODULE_PREFIX = 'parietal_lobe.parietal_mcp.mcp_ticket_functions.mcp_ticket_'


class TicketType(str, Enum):
    EPIC = 'EPIC'
    STORY = 'STORY'
    TASK = 'TASK'


ALLOWED_ACTIONS = {a.value for a in TicketAction}
ALLOWED_TYPES = {t.value for t in TicketType}


async def route(action: str, **kwargs) -> str:
    """
    Central routing for ticket operations.

    This router now forwards a flat set of keyword arguments directly to the
    underlying handler. The handlers are responsible for validating any
    action-specific requirements (e.g., item_type for create/search).
    """
    action = str(action).lower()

    if action not in ALLOWED_ACTIONS:
        return (
            "Error: Invalid action "
            f"'{action}'. Must be one of: {', '.join(sorted(ALLOWED_ACTIONS))}."
        )

    # Map 'comment' action to 'comment_add' module
    module_action = 'comment_add' if action == 'comment' else action
    module_path = f'{MODULE_PREFIX}{module_action}'

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        logger.error(
            f'[mcp_ticket_router] Module not found: {module_path}. Error: {e}'
        )
        return f"Error: Ticket action '{action}' module not found."

    execute_fn = getattr(module, 'execute', None)
    if not execute_fn:
        return f"Error: Ticket action '{action}' has no execute function."

    try:
        return await execute_fn(**kwargs)
    except TypeError as e:
        return f'Error: Invalid parameters for ticket {action}: {str(e)}'
    except Exception as e:
        logger.exception(f'[mcp_ticket_router] Execution crash in {action}')
        return f'Error: ticket {action} execution failed: {str(e)}'
