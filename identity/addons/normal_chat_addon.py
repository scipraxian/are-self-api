from typing import Any, Dict, List
from frontal_lobe.models import ReasoningTurn

def normal_chat_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: HISTORY):
    Standard chronological chat history. No eviction, no warnings.
    """
    if not turn or not turn.session:
        return []

    history_qs = list(
        ReasoningTurn.objects.filter(
            session_id=turn.session.id,
            turn_number__lt=turn.turn_number,
            model_usage_record__isnull=False
        )
        .select_related('model_usage_record')
        .order_by('turn_number')
    )

    history_array = []
    for prev_turn in history_qs:
        req_payload = prev_turn.model_usage_record.request_payload or []
        res_payload = prev_turn.model_usage_record.response_payload or {}
        
        if isinstance(req_payload, list):
            history_array.extend(req_payload)
        elif isinstance(req_payload, dict):
            history_array.append(req_payload)
            
        if isinstance(res_payload, list):
            history_array.extend(res_payload)
        elif isinstance(res_payload, dict):
            if "role" in res_payload:
                history_array.append(res_payload)
            elif "choices" in res_payload and len(res_payload["choices"]) > 0:
                history_array.append(res_payload["choices"][0].get("message", {}))

    return history_array