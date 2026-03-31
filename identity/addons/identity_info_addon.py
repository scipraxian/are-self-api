from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn
from identity.models import IdentityDisc


def identity_info_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: IDENTIFY)
    Injects the core system prompt, persona, and environmental rules.
    STRICTLY SYNCHRONOUS.
    """
    # it forced a local import.
    from identity.identity_prompt import build_identity_prompt

    if not turn.session.identity_disc:
        return []

    # Fetch the actual Disc object for the prompt builder
    disc = turn.session.identity_disc
    iteration_id = None
    if turn.session.participant_id:
        iteration_id = (
            turn.session.participant.iteration_shift.shift_iteration_id
        )

    prompt_text = build_identity_prompt(
        identity_disc=disc,
        iteration_id=iteration_id,
        turn_number=turn.turn_number,
        reasoning_turn_id=turn.id,
    )

    if not prompt_text:
        return []

    return [{'role': 'system', 'content': prompt_text}]
