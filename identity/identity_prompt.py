from typing import Optional

from identity.models import Identity, IdentityDisc

# TODO: resolve context so we can use django variables.


def render_base_identity(identity: Optional['Identity']) -> str:
    """
    Compiles the static persona, tags, and addons.
    Can be previewed directly from the Identity Admin.
    """
    if not identity:
        return 'No Identity provided. Operating with blank slate.'

    prompt_blocks = [identity.system_prompt_template]

    # M2M fields require the object to be saved first
    if identity.pk:
        tags = [tag.name for tag in identity.tags.all()]
        if tags:
            prompt_blocks.append(f'### Identity Tags ###\n[{", ".join(tags)}]')

        addons = identity.addons.all()
        if addons:
            prompt_blocks.append('### Identity Addons ###')
            for addon in addons:
                prompt_blocks.append(f'- {addon.name}: {addon.description}')

    return '\n\n'.join(prompt_blocks)


def build_identity_prompt(
    disc: Optional['IdentityDisc'], turn_number: int = 1
) -> str:
    """
    Dynamically compiles the system prompt based on the mounted IdentityDisc.
    Called by the Frontal Lobe before every turn.
    """
    if not disc or not disc.identity:
        return 'No Identity mounted. Operating with blank slate.'

    # 1. Get the base persona
    prompt_blocks = [render_base_identity(disc.identity)]

    # 2. Append Disc-specific runtime stats
    prompt_blocks.append(
        f'### Identity Disc Statistics ###\n'
        f'Level: {disc.level} | XP: {disc.xp} | '
        f'Tickets Closed: {disc.successes} | Turnouts: {disc.failures}'
    )

    # 3. Inject memory from previous sleep cycle (Turn 1 only)
    if turn_number == 1 and disc.last_message_to_self:
        prompt_blocks.append(
            f'### Message from your previous instance ###\n'
            f'"{disc.last_message_to_self}"'
        )

    return '\n\n'.join(prompt_blocks)
