from typing import Any, Dict, Optional

from parietal_lobe.parietal_mcp.mcp_ticket_functions.mcp_ticket__router import route


async def mcp_ticket(
    action: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    ticket_action: Optional[str] = None,
) -> str:
    """MCP Tool: Unified Agile ticket operations (EPIC, STORY, TASK).

    This tool can be invoked in two equivalent ways:

    - Legacy: mcp_ticket(action='create', params={...})
    - Enums-based: mcp_ticket(ticket_action='CREATE', params={...})

    Actions:
        - create: create a new EPIC/STORY/TASK
        - read:   read a ticket by UUID (type inferred)
        - update: patch a ticket by UUID (type inferred)
        - search: search tickets by type and text query
        - comment: add a comment to a specific ticket

    Params:
        - create:  {'item_type': 'EPIC|STORY|TASK', 'payload': {...}, 'parent_id': '...'(optional)}
        - read:    {'item_id': 'uuid-string'}
        - update:  {'item_id': 'uuid-string', 'payload': {...}}
        - search:  {'item_type': 'EPIC|STORY|TASK', 'query': 'text'}
        - comment: {'item_type': 'EPIC|STORY|TASK', 'item_id': 'uuid-string', 'text': 'comment'}

    All actions return a JSON string produced by a PFCActionResponseSerializer
    wrapper with fields: ok, action, item_type, item_id, data, error.
    """
    # Prefer explicit `action` when provided, otherwise fall back to ticket_action
    effective_action = (action or ticket_action or '').lower()
    if not effective_action:
        return (
            "Error: mcp_ticket requires either 'action' "
            "or 'ticket_action' to be provided."
        )

    params_dict: Dict[str, Any] = params or {}
    return await route(effective_action, params_dict)
