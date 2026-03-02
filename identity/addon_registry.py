import logging
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


def focus_game_modifier(
    iteration_id: Optional[int], identity_id: str, turn_number: int
) -> str:
    """
    Example Addon: Modifies the Focus Game rules based on how long the AI has been thinking.
    """
    if turn_number == 1:
        return 'Focus Game Status [FRESH]: Explore the problem space broadly. Do not rush to synthesize.'
    elif turn_number <= 5:
        return 'Focus Game Status [ENGAGED]: You have gathered initial data. Begin narrowing your hypothesis.'
    else:
        return 'Focus Game Status [FATIGUE WARNING]: You are burning excessive compute. Synthesize your findings immediately and call mcp_done.'


# The master lookup dict for function_slugs
ADDON_REGISTRY: Dict[str, Callable[[Optional[int], str, int], str]] = {
    'focus_game_dynamic': focus_game_modifier,
    # Add future slugs here (e.g., 'system_health_monitor', 'agile_urgency')
}
