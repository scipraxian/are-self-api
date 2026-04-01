import logging

from asgiref.sync import sync_to_async

from frontal_lobe.models import ReasoningTurn

logger = logging.getLogger(__name__)


async def mcp_internal_monologue(
    thought: str,
    note_for_next_turn: str,
    message_to_user: str = '',
    session_id: str = None,
    turn_id: int = None,
    **kwargs,
) -> str:
    """
    MANDATORY Cognitive Tool.
    Allows the model to reason, speak to the user, and pass notes to its future self.
    """
    logger.info(f'[INTERNAL MONOLOGUE] Recorded for Turn {turn_id}.')
    return f'Cognitive state recorded. NOTE FOR NEXT TURN: {note_for_next_turn}'
