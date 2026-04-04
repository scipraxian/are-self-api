from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn


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
