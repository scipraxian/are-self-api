import logging

from asgiref.sync import sync_to_async

from talos_hippocampus.models import TalosEngram, TalosEngramTag
from talos_reasoning.models import ReasoningSession

logger = logging.getLogger(__name__)


@sync_to_async
def _save_sync(
    session_id: str,
    title: str,
    fact: str,
    tags: str = '',
    relevance: float = 1.0,
) -> str:
    try:
        session = ReasoningSession.objects.get(id=session_id)
        latest_turn = session.turns.last()

        # The name is now the human-readable Index Title, not a hash
        engram = TalosEngram.objects.create(
            name=title[:254], description=fact, relevance_score=relevance
        )

        engram.sessions.add(session)
        if latest_turn:
            engram.source_turns.add(latest_turn)

        if tags:
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            for t_name in tag_list:
                tag_obj, _ = TalosEngramTag.objects.get_or_create(name=t_name)
                engram.tags.add(tag_obj)

        return (
            f'Success: Memory Card [{engram.id}: {engram.name}] crystallized.'
        )
    except Exception as e:
        return f'Memory Error: {str(e)}'


async def mcp_save_memory(
    session_id: str,
    title: str,
    fact: str,
    tags: str = '',
    relevance: float = 1.0,
) -> str:
    """MCP Tool: Crystallizes a fact into an Engram card with a descriptive title."""
    return await _save_sync(session_id, title, fact, tags, relevance)
