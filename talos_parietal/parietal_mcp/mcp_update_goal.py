import logging

from asgiref.sync import sync_to_async

from talos_reasoning.models import (
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatusID,
)

logger = logging.getLogger(__name__)


@sync_to_async
def _update_goal_sync(
    session_id: str, goal_action: str, goal_text: str = '', goal_id: int = None
) -> str:

    try:
        session = ReasoningSession.objects.get(id=session_id)
        goal_action = goal_action.upper()

        if goal_action == 'CREATE':
            goal = ReasoningGoal.objects.create(
                session=session,
                rendered_goal=goal_text,
                status_id=ReasoningStatusID.ACTIVE,
            )
            return (
                f'Success: Goal [ID: {goal.id}] created. Waking state updated.'
            )

        elif goal_action == 'COMPLETE':
            if not goal_id:
                return 'Error: goal_id required for COMPLETE action.'
            goal = ReasoningGoal.objects.get(id=goal_id, session=session)
            goal.achieved = True
            goal.status_id = ReasoningStatusID.COMPLETED
            goal.save()
            return f'Success: Goal [ID: {goal.id}] marked complete. Removed from waking state.'

        elif goal_action == 'UPDATE':
            if not goal_id:
                return 'Error: goal_id required for UPDATE action.'
            goal = ReasoningGoal.objects.get(id=goal_id, session=session)
            goal.rendered_goal = goal_text
            goal.save()
            return f'Success: Goal [ID: {goal.id}] updated.'

        return f"Error: Unknown action '{goal_action}'. Use CREATE, COMPLETE, or UPDATE."
    except Exception as e:
        logger.error(f'[Parietal] Goal update failed: {e}')
        return f'Goal Update Error: {str(e)}'


async def mcp_update_goal(
    session_id: str, goal_action: str, goal_text: str = '', goal_id: int = None
) -> str:
    """
    MCP Tool: Manages dynamic objectives across sleep cycles.
    Actions: CREATE, COMPLETE, UPDATE.
    """
    return await _update_goal_sync(session_id, goal_action, goal_text, goal_id)
