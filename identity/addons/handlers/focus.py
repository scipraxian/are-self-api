"""Focus Game handler.

Owns the per-tool Focus economy (fizzle check + Focus/XP ledger) AND the
per-turn Focus pool prompt block. This is the single source of truth for the
Focus Game — if the IdentityAddon row pointing at this handler isn't attached
to a disc, the game is off for that disc.

Ported from identity/addons/focus_addon.py; logic-equivalent, just
reorganized onto the IdentityAddonHandler lifecycle.
"""
from typing import Any, Dict, List, Optional

from frontal_lobe.models import ReasoningSession, ReasoningTurn
from identity.addons._handler import IdentityAddonHandler


class Focus(IdentityAddonHandler):
    def on_context(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
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
        _was_efficient, efficiency_status = turn.apply_efficiency_bonus()
        if efficiency_status:
            prompt_blocks.append(
                f'### Efficiency Bonus ###\n{efficiency_status}'
            )

        current_turn = turn.turn_number
        level_up_str = (
            ' | [LEVEL UP! Focus Pool Fully Restored]'
            if session.current_focus == session.max_focus and current_turn > 1
            else ''
        )
        prompt_blocks.append('### Focus Pool Statistics ###')
        prompt_blocks.append(
            f'Focus Pool: {session.current_focus} / '
            f'{session.max_focus}{level_up_str}'
        )

        if session.current_focus == 0:
            prompt_blocks.append(
                'DANGER: FOCUS POOL EMPTY. Use a generator if you can or '
                'mcp_pass to restore.'
            )

        return [{'role': 'system', 'content': '\n\n'.join(prompt_blocks)}]

    def on_tool_pre(
        self, session: ReasoningSession, mechanics: Any
    ) -> Optional[str]:
        """Return a fizzle message if the session lacks Focus for this cost."""
        focus_mod = mechanics.focus_modifier if mechanics is not None else 0
        if focus_mod >= 0:
            return None
        if session.current_focus + focus_mod >= 0:
            return None
        return (
            f'SYSTEM OVERRIDE: Effector Fizzled! Insufficient Focus. '
            f'(Requires {-focus_mod}, but you only have '
            f'{session.current_focus}). '
            f'You must use Synthesis tools (like mcp_engram_save) to '
            f'restore Focus.'
        )

    def on_tool_post(
        self,
        session: ReasoningSession,
        mechanics: Any,
        result: Any,
    ) -> None:
        """Apply the Focus/XP delta for this tool call.

        `result` is the raw tool_result object (pre-stringification) so
        `focus_yield`/`xp_yield` attribute overrides are observable.
        """
        focus_mod = mechanics.focus_modifier if mechanics is not None else 0
        xp_gain = mechanics.xp_reward if mechanics is not None else 0

        if hasattr(result, 'focus_yield'):
            focus_mod = getattr(result, 'focus_yield')
        if hasattr(result, 'xp_yield'):
            xp_gain = getattr(result, 'xp_yield')

        session.current_focus = max(
            0, min(session.max_focus, session.current_focus + focus_mod)
        )
        session.total_xp += xp_gain
        session.save(update_fields=['current_focus', 'total_xp'])
