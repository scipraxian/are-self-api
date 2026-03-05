import logging
from typing import Optional
from uuid import UUID

from identity.addons.addon_registry import ADDON_REGISTRY

from .addons.addon_package import AddonPackage
from .models import Identity, IdentityAddon, IdentityDisc

logger = logging.getLogger(__name__)


def render_base_identity(
    identity: Optional['Identity'],
    iteration_id: Optional[int] = None,
    turn_number: int = 1,
    identity_disc: Optional['IdentityDisc'] = None,
    reasoning_turn_id: Optional[int] = None,
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
                    addon,
                    identity.id,
                    identity_disc.id,
                    iteration_id,
                    turn_number,
                    reasoning_turn_id,
                )
                prompt_blocks.append(block_text)

    return '\n\n'.join(prompt_blocks)


def _resolve_addon_content(
    addon: 'IdentityAddon',
    identity_id: UUID,
    identity_disc_id: Optional[UUID],
    iteration_id: Optional[int],
    turn_number: int,
    reasoning_turn_id: Optional[int],
) -> str:
    """Safely executes the dynamic addon function or falls back to static text."""
    slug = addon.function_slug

    if slug and slug in ADDON_REGISTRY:
        package = AddonPackage(
            iteration=iteration_id,
            identity=identity_id,
            identity_disc=identity_disc_id,
            turn_number=turn_number,
            reasoning_turn_id=reasoning_turn_id,
        )
        try:
            dynamic_text = ADDON_REGISTRY[slug](package)
            return f'- {addon.name}:\n{dynamic_text}'
        except Exception as e:
            logger.error(f"Addon '{slug}' failed to execute: {e}")
            return f'- {addon.name}: [System Error: Dynamic module failed]'

    # Fallback to static description if no slug or slug not found
    return f'- {addon.name}: {addon.description}'


def build_identity_prompt(
    identity_disc: Optional['IdentityDisc'],
    iteration_id: Optional[int] = None,
    turn_number: int = 1,
    reasoning_turn_id: Optional[int] = None,
) -> str:
    """
    Dynamically compiles the system prompt based on the mounted IdentityDisc.
    Called by the Frontal Lobe before every turn.
    """
    if not identity_disc or not identity_disc.identity:
        return 'No Identity mounted. Operating with blank slate.'

    prompt_blocks = [
        render_base_identity(
            identity=identity_disc.identity,
            identity_disc=identity_disc,
            iteration_id=iteration_id,
            turn_number=turn_number,
            reasoning_turn_id=reasoning_turn_id,
        )
    ]

    if turn_number == 1 and identity_disc.last_message_to_self:
        prompt_blocks.append(
            f'### Message from previous instance ###\n'
            f'"{identity_disc.last_message_to_self}"'
        )

    return '\n\n'.join(prompt_blocks)
