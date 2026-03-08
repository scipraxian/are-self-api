import logging
from typing import Optional

from .addon_registry import ADDON_REGISTRY
from .models import Identity, IdentityAddon, IdentityDisc

logger = logging.getLogger(__name__)


def render_base_identity(
    identity: Optional['Identity'],
    iteration_id: Optional[int] = None,
    turn_number: int = 1,
) -> str:
    """
    Compiles the static persona, tags, and dynamically executes Addons.
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
                block_text = _resolve_addon_content(
                    addon, str(identity.id), iteration_id, turn_number
                )
                prompt_blocks.append(block_text)

    return '\n\n'.join(prompt_blocks)


def _resolve_addon_content(
    addon: 'IdentityAddon',
    identity_id: str,
    iteration_id: Optional[int],
    turn_number: int,
) -> str:
    """Safely executes the dynamic addon function or falls back to static text."""
    slug = addon.function_slug

    if slug and slug in ADDON_REGISTRY:
        try:
            dynamic_text = ADDON_REGISTRY[slug](
                iteration_id=iteration_id,
                identity_id=identity_id,
                turn_number=turn_number,
            )
            return f'- {addon.name}:\n{dynamic_text}'
        except Exception as e:
            logger.error(f"Addon '{slug}' failed to execute: {e}")
            return f'- {addon.name}: [System Error: Dynamic module failed]'

    # Fallback to static description if no slug or slug not found
    return f'- {addon.name}: {addon.description}'


def build_identity_prompt(
    disc: Optional['IdentityDisc'],
    iteration_id: Optional[int] = None,
    turn_number: int = 1,
) -> str:
    """
    Dynamically compiles the system prompt based on the mounted IdentityDisc.
    Called by the Frontal Lobe before every turn.
    """
    if not disc or not disc.identity:
        return 'No Identity mounted. Operating with blank slate.'

    # 1. Get the base persona (executing dynamic addons)
    prompt_blocks = [
        render_base_identity(disc.identity, iteration_id, turn_number)
    ]

    # 2. Append Disc-specific runtime stats
    prompt_blocks.append(
        f'### Identity Disc Statistics ###\n'
        f'Level: {disc.level} | XP: {disc.xp} | '
        f'Tickets Closed: {disc.successes} | Turnouts: {disc.failures}'
    )

    # 3. Inject memory from previous sleep cycle (Turn 1 only)
    if turn_number == 1 and disc.last_message_to_self:
        prompt_blocks.append(
            f'### Message from previous instance ###\n'
            f'"{disc.last_message_to_self}"'
        )

    return '\n\n'.join(prompt_blocks)
