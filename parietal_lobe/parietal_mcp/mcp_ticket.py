from parietal_lobe.parietal_mcp.mcp_ticket_functions.mcp_ticket__router import route

async def mcp_ticket(action: str, params: dict) -> str:
    """MCP Tool: Unified Agile ticket operations (EPIC, STORY, TASK).

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
    return await route(action, params)
