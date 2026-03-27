import json
import logging

from asgiref.sync import sync_to_async

from frontal_lobe.models import ReasoningSession, ReasoningStatusID

logger = logging.getLogger(__name__)


async def mcp_respond_to_user(
    thought: str,
    message_to_user: str,
    note_for_next_turn: str,
    yield_turn: bool = False,
    session_id: str = None,
    turn_id: str = None,
    **kwargs,
) -> str:
    """Unified communication tool. Replaces mcp_internal_monologue and mcp_ask_user.

    The model uses this tool every time it wants to think, speak, or pause.
    When yield_turn is True, the session is paused and the human is notified.
    When yield_turn is False, the loop continues and the model keeps working.

    Args:
        thought: The model's internal reasoning for this action.
        message_to_user: Text displayed directly to the human. Can be empty
            if the model is just thinking.
        note_for_next_turn: A concise factual summary carried to the next turn
            as the model's short-term memory.
        yield_turn: When True, pauses the session and waits for human input.
            When False, the reasoning loop continues immediately.
        session_id: Injected automatically by the Parietal Lobe gateway.
        turn_id: Injected automatically by the Parietal Lobe gateway.
    """
    if yield_turn and session_id:
        try:
            session = await sync_to_async(ReasoningSession.objects.get)(
                id=session_id
            )
            if session.status_id == ReasoningStatusID.ACTIVE:
                session.status_id = ReasoningStatusID.ATTENTION_REQUIRED
                await sync_to_async(session.save)(update_fields=['status_id'])
                logger.info(
                    '[mcp_respond_to_user] Session %s yielded to human.',
                    session_id,
                )
        except ReasoningSession.DoesNotExist:
            logger.error(
                '[mcp_respond_to_user] Session %s not found.', session_id
            )
        except Exception as e:
            logger.error(
                '[mcp_respond_to_user] Failed to yield session %s: %s',
                session_id,
                e,
            )

    action = 'YIELDED — Waiting for human.' if yield_turn else 'CONTINUING'
    return f'Cognitive state recorded. {action}. NOTE FOR NEXT TURN: {note_for_next_turn}'
