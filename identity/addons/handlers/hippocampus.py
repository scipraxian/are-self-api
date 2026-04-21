"""Hippocampus memory-retrieval handler."""
from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn
from hippocampus.hippocampus import Hippocampus
from identity.addons._handler import IdentityAddonHandler


class Hippocampus_(IdentityAddonHandler):
    """Handler for the Hippocampus addon.

    Class name has a trailing underscore so it doesn't collide with the
    imported `Hippocampus` service class. `addon_class_name` on the
    IdentityAddon row should be `'Hippocampus_'` to match.
    """

    def on_context(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
        if not turn or not turn.session:
            return []

        current_turn = turn.turn_number

        if current_turn == 1 and turn.session.spike:
            catalog_block = Hippocampus.get_turn_1_catalog(turn.session.spike)
        else:
            catalog_block = Hippocampus.get_recent_catalog(turn.session)

        if not catalog_block:
            return []

        return [{'role': 'system', 'content': catalog_block}]
