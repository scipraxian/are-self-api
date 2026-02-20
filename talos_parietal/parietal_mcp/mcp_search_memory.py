from asgiref.sync import sync_to_async
from django.db.models import Q

from talos_hippocampus.models import TalosEngram


@sync_to_async
def _search_sync(query: str = '', tags: str = '', limit: int = 10) -> str:
    qs = TalosEngram.objects.filter(is_active=True)

    if query:
        qs = qs.filter(
            Q(description__icontains=query) | Q(name__icontains=query)
        )
    if tags:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]
        qs = qs.filter(tags__name__in=tag_list)

    qs = qs.distinct().order_by('-relevance_score', '-created')[:limit]

    if not qs.exists():
        return 'No memories found matching criteria.'

    results = [
        'Found memory cards (Use mcp_read_engram to read the full fact):'
    ]
    for m in qs:
        tag_str = ', '.join([t.name for t in m.tags.all()])
        # Return ONLY the index data.
        results.append(
            f'ID {m.id} | Title: {m.name} | Tags: [{tag_str}] | Rel: {m.relevance_score}'
        )

    return '\n'.join(results)


async def mcp_search_memory(query: str = '', tags: str = '') -> str:
    """MCP Tool: Searches long-term memory. Returns IDs and Titles only."""
    return await _search_sync(query, tags)
