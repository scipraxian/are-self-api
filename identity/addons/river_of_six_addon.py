from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn


def river_of_six_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: HISTORY):
    Retains 6 turns of history, decaying tool data to enforce Engram usage.
    """
    if not turn or not turn.session:
        return []

    current_turn_num = turn.turn_number
    cutoff_turn = max(1, current_turn_num - 6)

    history_qs = list(
        ReasoningTurn.objects.filter(
            session_id=turn.session.id,
            turn_number__gte=cutoff_turn,
            turn_number__lt=current_turn_num,
            model_usage_record__isnull=False,
        )
        .select_related('model_usage_record')
        .order_by('turn_number')
    )

    history_array = []

    for prev_turn in history_qs:
        age = current_turn_num - prev_turn.turn_number
        req_payload = prev_turn.model_usage_record.request_payload or []
        res_payload = prev_turn.model_usage_record.response_payload or {}

        # 1. Grab tools and the single final user prompt that initiated this turn
        for msg in req_payload:
            if msg.get('role') == 'tool':
                if age >= 4:
                    msg['content'] = (
                        '[DATA EVICTED FROM L1 CACHE. REQUIRES ENGRAM RETRIEVAL.]'
                    )
                elif age == 3:
                    msg['content'] = (
                        str(msg.get('content', ''))
                        + '\n\n[SYSTEM CRITICAL: L1 EVICTION IMMINENT ON NEXT TURN. FINAL CHANCE TO SAVE TO ENGRAMS.]'
                    )
                elif age == 2:
                    msg['content'] = (
                        str(msg.get('content', ''))
                        + '\n\n[SYSTEM WARNING: L1 Cache decay beginning.]'
                    )
                history_array.append(msg)

        user_msgs = [m for m in req_payload if m.get('role') == 'user']
        if user_msgs:
            history_array.append(user_msgs[-1])  # Only append the new prompt!

        # 2. Grab the single assistant response that concluded this turn
        if isinstance(res_payload, dict):
            if 'role' in res_payload:
                history_array.append(res_payload)
            elif 'choices' in res_payload and len(res_payload['choices']) > 0:
                history_array.append(
                    res_payload['choices'][0].get('message', {})
                )

    return history_array
