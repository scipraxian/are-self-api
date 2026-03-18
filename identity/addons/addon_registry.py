import logging
from typing import Callable, Dict, List

from frontal_lobe.models import ChatMessage
from identity.addons.addon_package import AddonPackage
from identity.addons.agile_addon import agile_addon
from identity.addons.deadline_addon import deadline_addon
from identity.addons.focus_addon import focus_addon
from identity.addons.hippocampus_addon import hippocampus_addon
from identity.addons.identity_info_addon import identity_info_addon
from identity.addons.normal_chat_addon import normal_chat_addon
from identity.addons.river_of_six_addon import river_of_six_addon
from identity.addons.telemetry_addon import telemetry_addon
from identity.addons.your_move_addon import your_move_addon

logger = logging.getLogger(__name__)

# The master lookup dict. Strictly typed to require a synchronous List return.
ADDON_REGISTRY: Dict[str, Callable[[AddonPackage], List[ChatMessage]]] = {
    'agile_addon': agile_addon,
    'deadline_addon': deadline_addon,
    'focus_addon': focus_addon,
    'hippocampus_addon': hippocampus_addon,
    'identity_info_addon': identity_info_addon,
    'normal_chat_addon': normal_chat_addon,
    'river_of_six_addon': river_of_six_addon,
    'telemetry_addon': telemetry_addon,
    'your_move_addon': your_move_addon,
}
