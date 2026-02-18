from asgiref.sync import sync_to_async
from django.db.models import Q


@sync_to_async
def _search_sync(query: str = '', tags: str = '', limit: int = 5) -> str:
    from talos_hippocampus.models import TalosEngram

    # Start with all active engrams
    qs = TalosEngram.objects.filter(is_active=True)

    # 1. Filter by Text Content (if provided)
    if query:
        qs = qs.filter(
            Q(description__icontains=query) | Q(name__icontains=query)
        )

    # 2. Filter by Tags (if provided)
    if tags:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]
        qs = qs.filter(tags__name__in=tag_list)

    # Deduplicate and order by relevance
    qs = qs.distinct().order_by('-relevance_score', '-created')[:limit]

    if not qs.exists():
        return 'No memories found matching criteria.'

    results = [f'Found {len(qs)} memories:']
    for m in qs:
        # We define a stable ID format for the AI to reference later
        tag_str = ', '.join([t.name for t in m.tags.all()])
        results.append(
            f'--- [Memory ID: {m.id}] ---\nFact: {m.description}\nTags: {tag_str}\nRelevance: {m.relevance_score}'
        )

    return '\n'.join(results)


async def mcp_search_memory(query: str = '', tags: str = '') -> str:
    """
    MCP Tool: Searches long-term memory.
    args:
        query: Text to search for (e.g., 'NinjaLive error').
        tags: Filter by tags (e.g., 'fix, critical').
    """
    return await _search_sync(query, tags)
