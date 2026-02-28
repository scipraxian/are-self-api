from frontal_lobe.models import ReasoningSession


def build_identity_prompt(session: ReasoningSession, turn_number: int) -> str:
    """
    Dynamically compiles the system prompt based on the mounted IdentityDisc.
    Called by the Frontal Lobe before every turn.
    """
    disc = session.identity
    prompt_blocks = [disc.identity.system_prompt_template]
    tags = [tag.name for tag in disc.identity.tags.all()]
    if tags:
        prompt_blocks.append(f'### Identity Tags ###\n[{", ".join(tags)}]')
    addons = disc.identity.addons.all()
    if addons:
        prompt_blocks.append('### Identity Addons ###')
        for addon in addons:
            prompt_blocks.append(f'- {addon.name}: {addon.description}')
    prompt_blocks.append(
        f'### Identity Disc Statistics ###\n'
        f'Level: {disc.level} | XP: {disc.xp} | '
        f'Tickets Closed: {disc.successes} | Turnouts: {disc.failures}'
    )
    if turn_number == 1 and disc.last_message_to_self:
        prompt_blocks.append(
            f'### Message from your previous instance ###\n'
            f'"{disc.last_message_to_self}"'
        )

    return '\n\n'.join(prompt_blocks)
