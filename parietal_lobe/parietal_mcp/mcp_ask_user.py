import json
import logging

from asgiref.sync import sync_to_async

from frontal_lobe.models import ReasoningSession, ReasoningStatusID

logger = logging.getLogger(__name__)


async def mcp_ask_user(
    question: str,
    session_id: str,
    details: str = '',
) -> str:
    """
    MCP Tool: Request human input and pause the current reasoning session.
    """
    try:
        session = await sync_to_async(ReasoningSession.objects.get)(
            id=session_id
        )
    except ReasoningSession.DoesNotExist:
        return json.dumps(
            {
                'ok': False,
                'error': f'Could not find ReasoningSession {session_id}.',
            }
        )

    if session.status_id != ReasoningStatusID.ACTIVE:
        return json.dumps(
            {
                'ok': False,
                'error': f'Cannot request attention. Session is currently {session.status_id}.',
            }
        )

    # 1. Update the database state, this causes a signal.
    session.status_id = ReasoningStatusID.ATTENTION_REQUIRED
    await sync_to_async(session.save)(update_fields=['status_id'])

    clean_q = (question or '').strip()
    clean_details = (details or '').strip()

    return json.dumps(
        {
            'ok': True,
            'action': 'ask_user',
            'message': 'Session paused successfully. The human has been notified. Their response will appear as the next message when this session resumes.',
            'question_asked': clean_q,
            'details_provided': clean_details,
        }
    )
