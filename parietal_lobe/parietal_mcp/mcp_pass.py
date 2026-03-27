from asgiref.sync import sync_to_async

from frontal_lobe.models import ReasoningSession


async def mcp_pass(thought: str = '', session_id: str = None) -> str:
    """Passes the turn. Focus pool fully restored."""
    if not session_id:
        return 'Turn passed, but no Session ID provided to restore Focus.'

    try:
        session = await sync_to_async(ReasoningSession.objects.get)(
            id=session_id
        )
        session.current_focus = session.max_focus
        await sync_to_async(session.save)(update_fields=['current_focus'])
        return f'Turn passed. Focus pool fully restored to {session.max_focus}.'
    except ReasoningSession.DoesNotExist:
        return 'Turn passed, but could not find Session to restore Focus.'
