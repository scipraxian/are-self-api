import json
from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn

def river_of_six_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: HISTORY):
    A highly constrained memory window. Retains 6 turns of history,
    gradually decaying tool data to simulate cognitive load and enforce Engram usage.
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
            model_usage_record__isnull=False
        )
        .select_related('model_usage_record')
        .order_by('turn_number')
    )

    history_array = []

    for prev_turn in history_qs:
        age = current_turn_num - prev_turn.turn_number
        
        req_payload = prev_turn.model_usage_record.request_payload or []
        res_payload = prev_turn.model_usage_record.response_payload or {}

        # The response payload from LiteLLM typically encapsulates the choices.
        # But Phase 3 says "Extract and concatenate their request_payload and response_payload JSON."
        # This implies request_payload is a List[Dict], and response_payload is a List[Dict] or single Dict message.
        
        turn_messages = []
        if isinstance(req_payload, list):
            turn_messages.extend(req_payload)
        elif isinstance(req_payload, dict):
            turn_messages.append(req_payload)

        # Assuming response_payload is the dictionary returned for Assistant, e.g. {"role": "assistant", ...}
        # Wait, litellm returns a full response dump, usually choices[0].message
        if isinstance(res_payload, list):
            turn_messages.extend(res_payload)
        elif isinstance(res_payload, dict):
            if "role" in res_payload:
                turn_messages.append(res_payload)
            elif "choices" in res_payload and len(res_payload["choices"]) > 0:
                turn_messages.append(res_payload["choices"][0].get("message", {}))

        for msg in turn_messages:
            if msg.get("role") == "tool":
                if age >= 4:
                    msg["content"] = '[DATA EVICTED FROM L1 CACHE. REQUIRES ENGRAM RETRIEVAL.]'
                elif age == 3:
                    msg["content"] = str(msg.get("content", "")) + '\n\n[SYSTEM CRITICAL: L1 EVICTION IMMINENT ON NEXT TURN. FINAL CHANCE TO SAVE TO ENGRAMS.]'
                elif age == 2:
                    msg["content"] = str(msg.get("content", "")) + '\n\n[SYSTEM WARNING: L1 Cache decay beginning.]'
            history_array.append(msg)

    return history_array
