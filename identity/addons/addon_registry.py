import logging
from typing import Any, Callable, Dict, List

from frontal_lobe.models import ReasoningTurn
from identity.addons.agile_addon import agile_addon
from identity.addons.deadline_addon import deadline_addon
from identity.addons.focus_addon import focus_addon
from identity.addons.hippocampus_addon import hippocampus_addon
from identity.addons.identity_info_addon import identity_info_addon
from identity.addons.memory_snapshot_addon import memory_snapshot_addon
from identity.addons.normal_chat_addon import normal_chat_addon
from identity.addons.platform_hint_addon import platform_hint_addon
from identity.addons.prompt_addon import prompt_addon
from identity.addons.river_of_six_addon import river_of_six_addon
from identity.addons.skills_index_addon import skills_index_addon
from identity.addons.telemetry_addon import telemetry_addon
from identity.addons.tool_guidance_addon import tool_guidance_addon
from identity.addons.your_move_addon import your_move_addon

logger = logging.getLogger(__name__)

# The master lookup dict. Strictly typed to require a synchronous List return.
ADDON_REGISTRY: Dict[str, Callable[[ReasoningTurn], List[Dict[str, Any]]]] = {
    'agile_addon': agile_addon,
    'deadline_addon': deadline_addon,
    'focus_addon': focus_addon,
    'hippocampus_addon': hippocampus_addon,
    'identity_info_addon': identity_info_addon,
    'memory_snapshot_addon': memory_snapshot_addon,
    'normal_chat_addon': normal_chat_addon,
    'platform_hint_addon': platform_hint_addon,
    'prompt_addon': prompt_addon,
    'river_of_six_addon': river_of_six_addon,
    'skills_index_addon': skills_index_addon,
    'telemetry_addon': telemetry_addon,
    'tool_guidance_addon': tool_guidance_addon,
    'your_move_addon': your_move_addon,
}
