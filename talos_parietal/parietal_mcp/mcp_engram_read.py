from asgiref.sync import sync_to_async

from talos_hippocampus.models import TalosEngram
from talos_reasoning.models import ReasoningSession


@sync_to_async
def _read_sync(session_id: str, engram_id: int) -> str:
    try:
        engram = TalosEngram.objects.get(id=engram_id, is_active=True)
        session = ReasoningSession.objects.get(id=session_id)

        # Pull it onto the active Murder Board
        engram.sessions.add(session)

        tags = ', '.join([t.name for t in engram.tags.all()])
        return f'--- ENGRAM {engram.id}: {engram.name} ---\nTags: {tags}\nFact: {engram.description}'
    except TalosEngram.DoesNotExist:
        return f'Error: Engram ID {engram_id} not found in Hippocampus.'
    except Exception as e:
        return f'Error: {str(e)}'


async def mcp_engram_read(session_id: str, engram_id: int) -> str:
    """MCP Tool: Reads the full fact of a specific Engram by ID."""
    return await _read_sync(session_id, engram_id)
