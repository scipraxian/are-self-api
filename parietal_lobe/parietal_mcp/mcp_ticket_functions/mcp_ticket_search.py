from typing import Optional

from asgiref.sync import sync_to_async

from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask
from prefrontal_cortex.serializers import TicketAction, make_action_response


MODEL_MAP = {
    'EPIC': PFCEpic,
    'STORY': PFCStory,
    'TASK': PFCTask,
}


def _search_models(query: str, models: dict) -> list[dict]:
    """Run icontains search across name/description for given models."""
    output: list[dict] = []
    for type_label, model_class in models.items():
        results = model_class.objects.filter(
            name__icontains=query
        ) | model_class.objects.filter(description__icontains=query)

        for item in results:
            output.append(
                {
                    'type': type_label,
                    'id': str(item.id),
                    'name': item.name,
                    'status': (
                        item.status.name if item.status else 'Unknown'
                    ),
                }
            )
    return output


@sync_to_async
def _search_sync(
    item_type: Optional[str], query: Optional[str]
) -> str:
    if not str(query or '').strip():
        return make_action_response(
            action=TicketAction.SEARCH,
            ok=False,
            item_type=str(item_type or '').upper(),
            error='Query must be a non-empty string.',
        )

    item_type_normalized = str(item_type or '').strip().upper()

    # Determine which models to search
    if item_type_normalized:
        if item_type_normalized not in MODEL_MAP:
            return make_action_response(
                action=TicketAction.SEARCH,
                ok=False,
                item_type=item_type_normalized,
                error='Invalid item type. Must be EPIC, STORY, or TASK.',
            )
        models_to_search = {
            item_type_normalized: MODEL_MAP[item_type_normalized]
        }
    else:
        models_to_search = MODEL_MAP

    query_stripped = str(query).strip()
    output = _search_models(query_stripped, models_to_search)

    # Limit to 10 to protect context window
    output = output[:10]

    return make_action_response(
        action=TicketAction.SEARCH,
        item_type=item_type_normalized or 'ALL',
        data={'results': output},
        ok=True,
    )


async def execute(
    item_type: Optional[str] = None,
    query: Optional[str] = None,
    **_: object,
) -> str:
    """Implementation of ticket search using flat arguments."""
    return await _search_sync(item_type=item_type, query=query)
