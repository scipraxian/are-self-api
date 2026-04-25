"""Identity info handler — injects persona + environmental rules at IDENTIFY."""
from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn
from identity.addons._handler import IdentityAddonHandler


class IdentityInfo(IdentityAddonHandler):
    def on_identify(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
        # Local import — circular if done at module scope.
        from identity.identity_prompt import build_identity_prompt

        if not turn.session.identity_disc:
            return []

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
