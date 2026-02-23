from asgiref.sync import sync_to_async

from talos_reasoning.models import (
    ReasoningSession,
    ReasoningStatusID,
    SessionConclusion,
)


@sync_to_async
def _conclude_sync(
    session_id: str,
    goal_achieved: bool,
    outcome_status: str,
    summary: str,
    recommended_action: str,
    next_goal_suggestion: str,
    system_persona_and_prompt_feedback: str,
) -> str:

    try:
        session = ReasoningSession.objects.get(id=session_id)

        # Update the Session Goal status based on AI report
        if session.goals.exists():
            main_goal = session.goals.first()
            main_goal.achieved = goal_achieved
            main_goal.save()

        # Create Conclusion
        SessionConclusion.objects.update_or_create(
            session=session,
            defaults=dict(
                outcome_status=outcome_status,
                summary=summary,
                recommended_action=recommended_action,
                next_goal_suggestion=next_goal_suggestion,
                system_persona_and_prompt_feedback=system_persona_and_prompt_feedback,
            ),
        )

        session.status_id = ReasoningStatusID.COMPLETED
        session.save(update_fields=['status'])

        return 'Session Concluded. Report filed.'

    except Exception as e:
        return f'Error: {str(e)}'


async def mcp_conclude_session(
    session_id: str,
    goal_achieved: bool,
    outcome_status: str,
    summary: str,
    recommended_action: str,
    next_goal_suggestion: str,
    system_persona_and_prompt_feedback: str,
) -> str:
    """
    MCP Tool: Files the final report.
    args:
        goal_achieved: True if you satisfied the user's objective, False otherwise.
        outcome_status: 'SUCCESS', 'FAILURE', 'PARTIAL'
    """
    return await _conclude_sync(
        session_id=session_id,
        goal_achieved=goal_achieved,
        outcome_status=outcome_status,
        summary=summary,
        recommended_action=recommended_action,
        next_goal_suggestion=next_goal_suggestion,
        system_persona_and_prompt_feedback=system_persona_and_prompt_feedback,
    )
