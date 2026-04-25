from typing import Any, Dict, List, Optional

from frontal_lobe.models import ReasoningSession, ReasoningTurn

# Registry slug. Must match the key in identity.addons.addon_registry.ADDON_REGISTRY.
# The parietal lobe gates the Focus Game mechanics (fizzle + focus/XP ledger) on
# whether an IdentityDisc has an IdentityAddon row with this slug attached — so a
# disc without the addon plays without the economy, and the addon is the single
# source of truth for Focus rules. Task 18 in NEURAL_MODIFIER_COMPLETION_PLAN.md
# will generalize this pattern into a proper lifecycle-hook contract; for now the
# three functions below (is_focus_addon_installed / check_fizzle / apply_delta)
# are the hand-rolled minimum that lets the parietal lobe delegate to the addon.
FOCUS_ADDON_SLUG = 'focus_addon'


def is_focus_addon_installed(identity_disc) -> bool:
    """Return True iff the Focus Game addon is attached to this IdentityDisc.

    Synchronous — wrap with `sync_to_async` at the caller when invoking from
    an async context. Safe to call with `identity_disc=None` (returns False).
    """
    if identity_disc is None:
        return False
    return identity_disc.addons.filter(function_slug=FOCUS_ADDON_SLUG).exists()


def check_fizzle(session: ReasoningSession, focus_mod: int) -> Optional[str]:
    """Return a fizzle message if the session lacks the Focus for this cost.

    Pure read, no mutation. Caller records the fizzle (ToolCall row + tool-result
    dict) in its own dispatch context. Returns None when the tool may proceed.
    """
    if focus_mod >= 0:
        return None
    if session.current_focus + focus_mod >= 0:
        return None
    return (
        f'SYSTEM OVERRIDE: Effector Fizzled! Insufficient Focus. '
        f'(Requires {-focus_mod}, but you only have {session.current_focus}). '
        f'You must use Synthesis tools (like mcp_engram_save) to restore Focus.'
    )


def apply_delta(
    session: ReasoningSession, focus_mod: int, xp_gain: int
) -> None:
    """Apply a Focus / XP delta to the session and persist.

    Synchronous — wrap with `sync_to_async` at the caller when invoking from
    an async context. Caps focus at `session.max_focus` on the upside and
    clamps at 0 on the downside (defensive — fizzle should prevent the
    negative path, but a post-execution `focus_yield` from a tool result
    could still drive a drain).
    """
    session.current_focus = max(
        0, min(session.max_focus, session.current_focus + focus_mod)
    )
    session.total_xp += xp_gain
    session.save(update_fields=['current_focus', 'total_xp'])


def focus_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Modifies the Focus Game rules based on how long the AI has been thinking.
    """
    if not turn:
        return []

    prompt_blocks = []
    session = turn.session

    if session.identity_disc:
        identity_disc = session.identity_disc
        prompt_blocks.append(
            f'### Identity Disc Statistics ###\n'
            f'Level: {identity_disc.level} | XP: {identity_disc.total_xp}'
        )
    else:
        prompt_blocks.append('Focus Addon Preview Mode (No Identity Disc)')

    # Apply the bonus (updates session focus natively)
    was_efficient, efficiency_status = turn.apply_efficiency_bonus()
    if efficiency_status:
        prompt_blocks.append(
            f'### Efficiency Bonus ###\n'
            f'{efficiency_status}'
        )

    current_turn = turn.turn_number
    level_up_str = (
        ' | [LEVEL UP! Focus Pool Fully Restored]'
        if session.current_focus == session.max_focus and current_turn > 1
        else ''
    )
    prompt_blocks.append('### Focus Pool Statistics ###')
    prompt_blocks.append(
        f'Focus Pool: {session.current_focus} / {session.max_focus}{level_up_str}'
    )

    if session.current_focus == 0:
        prompt_blocks.append(
            'DANGER: FOCUS POOL EMPTY. Use a generator if you can or mcp_pass to restore.'
        )

    # Return as a Volatile User message
    return [{'role': 'system', 'content': '\n\n'.join(prompt_blocks)}]
