"""Handler-pattern addons.

Each module here defines one IdentityAddonHandler subclass. The class name
is the canonical identifier — `IdentityAddon.addon_class_name` on the
row matches the class name here and is how the dispatcher resolves row → code.

This package is the live dispatch path. The older function-based addons at
`identity/addons/*_addon.py` remain on disk as deprecated fallback for any
row that still carries only `function_slug`; the handler path wins whenever
`addon_class_name` is populated.
"""
from identity.addons.handlers.agile import Agile
from identity.addons.handlers.deadline import Deadline
from identity.addons.handlers.focus import Focus
from identity.addons.handlers.hippocampus import Hippocampus_
from identity.addons.handlers.identity_info import IdentityInfo
from identity.addons.handlers.normal_chat import NormalChat
from identity.addons.handlers.prompt import Prompt
from identity.addons.handlers.river_of_six import RiverOfSix
from identity.addons.handlers.telemetry import Telemetry
from identity.addons.handlers.your_move import YourMove

__all__ = [
    'Agile',
    'Deadline',
    'Focus',
    'Hippocampus_',
    'IdentityInfo',
    'NormalChat',
    'Prompt',
    'RiverOfSix',
    'Telemetry',
    'YourMove',
]
