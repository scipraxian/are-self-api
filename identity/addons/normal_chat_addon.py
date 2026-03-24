from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn


def normal_chat_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: HISTORY):
    Standard chronological chat history. No eviction, no warnings.
    """
    if not turn or not turn.session:
        return []

    # Get the single most recent completed turn
    last_turn = (
        ReasoningTurn.objects.filter(
            session_id=turn.session.id,
            turn_number__lt=turn.turn_number,
            model_usage_record__isnull=False,
        )
        .select_related('model_usage_record')
        .order_by('-turn_number')
        .first()
    )

    if not last_turn:
        return []

    req = last_turn.model_usage_record.request_payload or []
    res = last_turn.model_usage_record.response_payload or {}

    # Clean the cumulative history (drop all system prompts to prevent duplication)
    clean_history = [m for m in req if m.get('role') != 'system']

    # Append the assistant's final answer from that turn
    if isinstance(res, dict):
        if 'role' in res:
            clean_history.append(res)
        elif 'choices' in res and len(res['choices']) > 0:
            clean_history.append(res['choices'][0].get('message', {}))

    return clean_history
