import json

from asgiref.sync import sync_to_async

from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask

MODEL_MAP = {
    'EPIC': PFCEpic,
    'STORY': PFCStory,
    'TASK': PFCTask,
}


@sync_to_async
def _search_sync(item_type: str, query: str) -> str:
    item_type = item_type.upper()
    if item_type not in MODEL_MAP:
        return 'Error: Invalid item type.'

    model_class = MODEL_MAP[item_type]
    # Simple OR search across name and description
    results = model_class.objects.filter(
        name__icontains=query
    ) | model_class.objects.filter(description__icontains=query)

    output = []
    for item in results[:10]:  # Limit to 10 to protect context window
        output.append(
            {
                'id': str(item.id),
                'name': item.name,
                'status': item.status.name if item.status else 'Unknown',
            }
        )

    if not output:
        return 'No results found.'
    return json.dumps(output, indent=2)


async def mcp_ticket_search(item_type: str, query: str) -> str:
    """MCP Tool: Searches the Agile board by item type and keyword query."""
    return await _search_sync(item_type, query)
