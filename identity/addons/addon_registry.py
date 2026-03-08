import logging
from typing import Callable, Dict

from identity.addons.addon_package import AddonPackage
from identity.addons.agile_addon import agile_addon
from identity.addons.focus_addon import focus_addon

logger = logging.getLogger(__name__)

# The master lookup dict for function_slugs
# Callable[[ArgumentType1], ReturnType]
ADDON_REGISTRY: Dict[str, Callable[[AddonPackage], str]] = {
    'focus_game_dynamic': focus_addon,
    'agile_addon': agile_addon,
}
