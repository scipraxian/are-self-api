from asgiref.sync import sync_to_async

from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask
from prefrontal_cortex.serializers import TicketAction, make_action_response


MODEL_MAP = {
    'EPIC': PFCEpic,
    'STORY': PFCStory,
    'TASK': PFCTask,
}


@sync_to_async
def _search_sync(item_type: str | None, query: str | None) -> str:
    item_type_normalized = str(item_type or '').upper()
    if item_type_normalized not in MODEL_MAP:
        return make_action_response(
            action=TicketAction.SEARCH,
            ok=False,
            item_type=item_type_normalized,
            error='Invalid item type. Must be EPIC, STORY, or TASK.',
        )

    if not str(query or '').strip():
        return make_action_response(
            action=TicketAction.SEARCH,
            ok=False,
            item_type=item_type_normalized,
            error='Query must be a non-empty string.',
        )

    model_class = MODEL_MAP[item_type_normalized]
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

    return make_action_response(
        action=TicketAction.SEARCH,
        item_type=item_type_normalized,
        data={'results': output},
        ok=True,
    )


async def execute(
    item_type: str | None = None,
    query: str | None = None,
    **_: object,
) -> str:
    """Implementation of ticket search using flat arguments."""
    return await _search_sync(item_type=item_type, query=query)
