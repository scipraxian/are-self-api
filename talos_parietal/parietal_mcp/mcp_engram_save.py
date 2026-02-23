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
        clean_title = title[:254]

        # 1. Check if it already exists
        existing_engram = TalosEngram.objects.filter(name=clean_title).first()
        if existing_engram:
            return (
                f"SYSTEM NOTICE: Engram '{clean_title}' already exists in your Hippocampus.\n"
                f'Current Fact: {existing_engram.description}\n'
                f'ACTION REQUIRED: If you wish to add new information to this, cast `mcp_engram_update`.'
            )

        # 2. If it doesn't exist, create it
        engram = TalosEngram.objects.create(
            name=clean_title, description=fact, relevance_score=relevance
        )

        engram.sessions.add(session)
        if latest_turn:
            engram.source_turns.add(latest_turn)

        if tags:
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            for t_name in tag_list:
                tag_obj, _ = TalosEngramTag.objects.get_or_create(name=t_name)
                engram.tags.add(tag_obj)

        return f'Success: Memory Card [{engram.id}: {engram.name}] permanently crystallized.'
    except Exception as e:
        return f'Memory Error: {str(e)}'


async def mcp_engram_save(
    session_id: str,
    title: str,
    fact: str,
    tags: str = '',
    relevance: float = 1.0,
) -> str:
    """MCP Tool: Crystallizes a NEW fact into an Engram card."""
    return await _save_sync(session_id, title, fact, tags, relevance)
