import logging

from asgiref.sync import sync_to_async

from talos_hippocampus.models import TalosEngram
from talos_reasoning.models import ReasoningSession

logger = logging.getLogger(__name__)


@sync_to_async
def _update_sync(session_id: str, title: str, additional_fact: str) -> str:
    try:
        clean_title = title[:254]
        # Lookup by the semantic name the AI sees in its HUD
        engram, _ = TalosEngram.objects.get_or_create(name=clean_title)
        session = ReasoningSession.objects.get(id=session_id)
        latest_turn = session.turns.last()

        # Append the new fact
        engram.description = (
            f'{engram.description}\n\n[UPDATE]: {additional_fact}'
        )
        engram.save(update_fields=['description'])

        # Ensure relationships are updated
        engram.sessions.add(session)
        if latest_turn:
            engram.source_turns.add(latest_turn)

        return f"Success: Engram '{engram.name}' has been updated with the new data."
    except TalosEngram.DoesNotExist:
        return f"Error: Engram with title '{clean_title}' does not exist. Use `mcp_engram_save` to create it first."
    except Exception as e:
        return f'Update Error: {str(e)}'


async def mcp_engram_update(
    session_id: str, title: str, additional_fact: str
) -> str:
    """MCP Tool: Appends new findings to an existing Engram."""
    return await _update_sync(session_id, title, additional_fact)
