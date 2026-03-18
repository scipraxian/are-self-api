import logging
from typing import Any, Callable, Coroutine, Dict, List, Union

from frontal_lobe.models import ChatMessage
from identity.addons import (
    hippocampus_addon,
    identity_info_addon,
    river_of_six_addon,
    telemetry_addon,
    your_move_addon,
)
from identity.addons.addon_package import AddonPackage
from identity.addons.agile_addon import agile_addon
from identity.addons.deadline_addon import deadline_addon
from identity.addons.focus_addon import focus_addon
from identity.addons.normal_chat_addon import normal_chat_addon

logger = logging.getLogger(__name__)

# Define a custom type that accepts either a standard list of messages,
# or an async coroutine that yields a list of messages.
AddonReturnType = Union[
    List[ChatMessage], Coroutine[Any, Any, List[ChatMessage]]
]

# The master lookup dict for function_slugs
ADDON_REGISTRY: Dict[str, Callable[[AddonPackage], AddonReturnType]] = dict(
    agile_addon=agile_addon,
    deadline_addon=deadline_addon,
    focus_addon=focus_addon,
    hippocampus_addon=hippocampus_addon,
    identity_info_addon=identity_info_addon,
    normal_chat_addon=normal_chat_addon,
    river_of_six_addon=river_of_six_addon,
    telemetry_addon=telemetry_addon,
    your_move_addon=your_move_addon,
)
