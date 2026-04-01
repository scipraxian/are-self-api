from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn
from hippocampus.hippocampus import Hippocampus


def hippocampus_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: CONTEXT)
    Retrieves the memory catalog and active engrams for the current turn.
    STRICTLY SYNCHRONOUS.
    """
    if not turn or not turn.session:
        return []

    current_turn = turn.turn_number

    # Execute the Hippocampus memory retrieval natively
    # (These methods are purely synchronous)
    if current_turn == 1 and turn.session.spike:
        catalog_block = Hippocampus.get_turn_1_catalog(turn.session.spike)
    else:
        catalog_block = Hippocampus.get_recent_catalog(turn.session)

    if not catalog_block:
        return []

    return [{'role': 'system', 'content': catalog_block}]
