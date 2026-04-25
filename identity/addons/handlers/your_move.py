"""Your-Move handler — the final TERMINAL nudge."""
from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn
from identity.addons._handler import IdentityAddonHandler


class YourMove(IdentityAddonHandler):
    def on_terminal(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
        content = (
            'YOUR MOVE:\n'
            '1. Address the current context or user request.\n'
            '2. You may use your available tools if data or actions are '
            'required.\n'
            '3. If no tools are needed, simply provide your response '
            'natively.\n'
        )
        return [{'role': 'system', 'content': content}]
