"""Deadline handler — injects remaining-turn warnings."""
from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn
from identity.addons._handler import IdentityAddonHandler


class Deadline(IdentityAddonHandler):
    def on_context(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
        if not turn:
            return [
                {
                    'role': 'user',
                    'content': 'Deadline Addon Preview Mode (No Reasoning Turn)',
                }
            ]

        session = turn.session
        current_turn = turn.turn_number
        max_turns = session.max_turns
        remaining_turns = max_turns - current_turn
        progress = current_turn / max_turns

        prompt_blocks = []
        percentage_remaining = round(progress * 100, 0)

        status = ''
        if remaining_turns == 1:
            status = 'CRITICAL:'
        elif remaining_turns <= 5:
            status = 'WARNING:'
        prompt_blocks.append(
            f'{status}{remaining_turns} of {max_turns} '
            f'TURNS REMAIN ({percentage_remaining}%).\n'
        )
        if remaining_turns == 1:
            prompt_blocks.append(
                '[LAST TURN. SUBMIT mcp_done or session will be DESTROYED.]'
            )
        elif remaining_turns <= 5:
            prompt_blocks.append(
                f'[CRITICAL: ONLY {remaining_turns} TURNS REMAIN.]'
            )

        return [
            {'role': 'system', 'content': '\n\n'.join(prompt_blocks)}
        ]
