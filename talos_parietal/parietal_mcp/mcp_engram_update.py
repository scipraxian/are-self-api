from asgiref.sync import sync_to_async

from talos_hippocampus.models import TalosEngram
from talos_reasoning.models import ReasoningSession


@sync_to_async
def _update_sync(session_id: str, title: str, additional_fact: str) -> str:
    try:
        clean_title = title[:254]
        engram = TalosEngram.objects.get(name=clean_title)
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
        return f"Error: Engram '{title}' does not exist. Use `mcp_engram_save` to create it first."
    except Exception as e:
        return f'Update Error: {str(e)}'


async def mcp_engram_update(
    session_id: str, title: str, additional_fact: str
) -> str:
    """MCP Tool: Appends new findings to an existing Engram."""
    return await _update_sync(session_id, title, additional_fact)
