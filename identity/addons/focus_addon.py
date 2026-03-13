from frontal_lobe.models import ReasoningTurn
from identity.addons.addon_package import AddonPackage
from identity.models import IdentityDisc


def focus_addon(package: AddonPackage) -> str:
    """
    Example Addon: Modifies the Focus Game rules based on how long the AI has been thinking.
    """
    prompt_blocks = []

    if package.identity_disc:
        identity_disc = IdentityDisc.objects.get(id=package.identity_disc)
        prompt_blocks.append(
            f'### Identity Disc Statistics ###\n'
            f'Level: {identity_disc.level} | XP: {identity_disc.xp}'
        )
    else:
        prompt_blocks.append(f'Focus Addon Preview Mode (No Identity Disc)')

    if package.reasoning_turn_id:
        turn_record = ReasoningTurn.objects.get(id=package.reasoning_turn_id)
        session = turn_record.session

        current_turn = turn_record.turn_number
        level_up_str = (
            ' | [LEVEL UP! Focus Pool Fully Restored]'
            if session.current_focus == session.max_focus and current_turn > 1
            else ''
        )
        prompt_blocks.append(f'### Focus Pool Statistics ###\n')
        prompt_blocks.append(
            f'Focus Pool: {session.current_focus} / {session.max_focus}{level_up_str}'
        )

        if session.current_focus == 0:
            prompt_blocks.append(
                f'DANGER: FOCUS POOL EMPTY. Use a generator if you can or mcp_pass to restore.'
            )
    else:
        prompt_blocks.append(f'Focus Addon Preview Mode (No Reasoning Turn)')

    return '\n\n'.join(prompt_blocks)
