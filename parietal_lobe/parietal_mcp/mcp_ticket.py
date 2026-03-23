from typing import Optional

from parietal_lobe.parietal_mcp.mcp_ticket_functions.mcp_ticket__router import (
    route,
)


async def mcp_ticket(
    action: Optional[str] = None,
    item_id: Optional[str] = None,
    item_type: Optional[str] = None,
    field_name: Optional[str] = None,
    field_value: Optional[str] = None,
    parent_id: Optional[str] = None,
    query: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """MCP Tool: Unified Agile ticket operations (EPIC, STORY, TASK).

    This tool uses a **flat, single-field** argument model. The LLM should
    perform atomic updates by calling the tool separately for each field it
    wants to set or change.

    Arguments:
        - action:     'create', 'read', 'update', 'search', or 'comment'.
        - item_id:    UUID of the target ticket (for read, update, comment).
        - item_type:  'EPIC', 'STORY', or 'TASK' (for create, search).
        - field_name: Exact model field name to update (for update).
        - field_value:
            - create:   Short ticket name/title.
            - update:   New value for the given field_name.
            - comment:  Comment body text.
        - parent_id:  UUID of parent ticket (Epic for Story, Story for Task).
        - query:      Search string (for search).

    All actions return a JSON string produced by a PFCActionResponseSerializer
    wrapper with fields: ok, action, item_type, item_id, data, error.
    """
    effective_action = (action or '').lower()
    if not effective_action:
        return "Error: mcp_ticket requires 'action' to be provided."

    return await route(
        effective_action,
        item_id=item_id,
        item_type=item_type,
        field_name=field_name,
        field_value=field_value,
        parent_id=parent_id,
        query=query,
        session_id=session_id,
    )
