"""Handler-pattern dispatch for IdentityAddon.

HANDLER_REGISTRY maps `IdentityAddon.addon_class_name` → handler class.
Dispatch is phase-aware: `dispatch_phase` picks the right lifecycle method
(`on_identify` / `on_context` / `on_history` / `on_terminal`) based on the
row's phase FK, so the frontal_lobe dispatch loop stays phase-agnostic.

Tool lifecycle dispatch (`dispatch_tool_pre`, `dispatch_tool_post`) is
first-veto on pre (Focus handler fizzles), collect-all on post (every
handler sees every tool result).

Handlers are instantiated as singletons at module import time — they're
stateless, so one instance per class is plenty.
"""
from typing import Any, Dict, List, Optional

from identity.addons.handlers import (
    Agile,
    Deadline,
    Focus,
    Hippocampus_,
    IdentityInfo,
    NormalChat,
    Prompt,
    RiverOfSix,
    Telemetry,
    YourMove,
)


# Phase FK id → lifecycle method name on IdentityAddonHandler.
# Matches identity.identityaddonphase fixture rows.
PHASE_METHOD = {
    1: 'on_identify',
    2: 'on_context',
    3: 'on_history',
    4: 'on_terminal',
}


# Canonical class-name → handler singleton map.
HANDLER_REGISTRY = {
    cls.__name__: cls()
    for cls in (
        Agile,
        Deadline,
        Focus,
        Hippocampus_,
        IdentityInfo,
        NormalChat,
        Prompt,
        RiverOfSix,
        Telemetry,
        YourMove,
    )
}


def handler_for(addon_model) -> Optional[Any]:
    """Return the handler singleton for this IdentityAddon row, or None."""
    name = getattr(addon_model, 'addon_class_name', None)
    if not name:
        return None
    return HANDLER_REGISTRY.get(name)


def handlers_for(disc) -> List[Any]:
    """Return handler singletons for every addon attached to this disc."""
    if disc is None:
        return []
    names = disc.addons.values_list('addon_class_name', flat=True)
    return [HANDLER_REGISTRY[n] for n in names if n and n in HANDLER_REGISTRY]


def dispatch_phase(
    addon_model, turn
) -> List[Dict[str, Any]]:
    """Call the handler method matching the addon row's phase FK.

    Returns [] if no handler, no phase, or no matching lifecycle method.
    """
    handler = handler_for(addon_model)
    if handler is None:
        return []
    phase_id = addon_model.phase_id
    method_name = PHASE_METHOD.get(phase_id) if phase_id else None
    if method_name is None:
        return []
    method = getattr(handler, method_name, None)
    if method is None:
        return []
    result = method(turn)
    return result or []


def dispatch_tool_pre(disc, session, mechanics) -> Optional[str]:
    """First-veto: any handler returning a non-None message fizzles the tool."""
    for h in handlers_for(disc):
        msg = h.on_tool_pre(session, mechanics)
        if msg is not None:
            return msg
    return None


def dispatch_tool_post(disc, session, mechanics, result) -> None:
    """Collect-all: every handler sees every tool post."""
    for h in handlers_for(disc):
        h.on_tool_post(session, mechanics, result)
