from identity.addons.addon_package import AddonPackage
from identity.models import IdentityDisc


def focus_addon(package: AddonPackage) -> str:
    """
    Example Addon: Modifies the Focus Game rules based on how long the AI has been thinking.
    """

    identity_disc = IdentityDisc.objects.get(id=package.identity_disc)
    turn_number = package.turn_number

    prompt_blocks = []

    # 2. Append Disc-specific runtime stats
    prompt_blocks.append(
        f'### Identity Disc Statistics ###\n'
        f'Level: {identity_disc.level} | XP: {identity_disc.xp} | '
        f'Tickets Closed: {identity_disc.successes} | Turnouts: {identity_disc.failures}'
    )

    if turn_number == 1:
        prompt_blocks.append(
            'Focus Game Status [FRESH]: Explore the problem space broadly. Do not rush to synthesize.'
        )
    elif turn_number <= 5:
        prompt_blocks.append(
            'Focus Game Status [ENGAGED]: You have gathered initial data. Begin narrowing your hypothesis.'
        )
    else:
        prompt_blocks.append(
            'Focus Game Status [FATIGUE WARNING]: You are burning excessive compute. Synthesize your findings immediately and call mcp_done.'
        )

    return '\n\n'.join(prompt_blocks)
