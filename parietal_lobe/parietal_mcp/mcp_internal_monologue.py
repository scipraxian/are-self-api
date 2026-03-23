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
    logger.info(f'[INTERNAL MONOLOGUE] Turn {turn_id} Thinking...')


    # 2. Save the thought process to the Turn record EVERY time
    if turn_id:
        try:
            turn_record = await sync_to_async(ReasoningTurn.objects.get)(
                id=turn_id
            )
            turn_record.thought_process = thought
            await sync_to_async(turn_record.save)(
                update_fields=['thought_process']
            )
        except Exception as e:
            logger.error(f'Failed to save thought_process to Turn: {e}')

    return f'Cognitive state recorded. NOTE FOR NEXT TURN: {note_for_next_turn}'
