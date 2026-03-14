import inspect
import logging
from typing import List, Optional, Tuple
from uuid import UUID

from asgiref.sync import async_to_sync

from identity.addons.addon_registry import ADDON_REGISTRY

from .addons.addon_package import AddonPackage
from .models import IdentityAddon, IdentityDisc

logger = logging.getLogger(__name__)


def render_base_identity(
    identity_disc: Optional['IdentityDisc'] = None,
    iteration_id: Optional[int] = None,
    turn_number: int = 1,
    reasoning_turn_id: Optional[int] = None,
) -> str:
    """
    Compiles the immutable system laws for the current IdentityDisc.

    This block is intentionally limited to the IdentityDisc.system_prompt_template
    (which encodes the IdentityDisc framing, Focus Economy, and cache rules)
    and optional static IdentityDisc metadata. Dynamic Addons and tags are
    emitted as separate chat messages by the Frontal Lobe.
    """
    if not identity_disc:
        return 'No Identity mounted. Operating with blank slate.'

    # Core system laws come directly from the IdentityDisc's system_prompt_template.
    prompt_blocks = [identity_disc.system_prompt_template or '']

    # Optionally surface which IdentityDisc is mounted, without mixing in
    # dynamic state or addon content.
    prompt_blocks.append(f'Identity Disc: {identity_disc.name}')

    return '\n\n'.join(block for block in prompt_blocks if block.strip())


def _resolve_addon_content(
    addon: 'IdentityAddon',
    identity_id: UUID,
    identity_disc_id: Optional[UUID],
    iteration_id: Optional[int],
    turn_number: int,
    reasoning_turn_id: Optional[int],
    environment_id: Optional[UUID] = None,
    shift_id: Optional[int] = None,
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
            environment_id=environment_id,
            shift_id=shift_id,
        )
        try:
            func = ADDON_REGISTRY[slug]
            if inspect.iscoroutinefunction(func):
                dynamic_text = async_to_sync(func)(package)
            else:
                dynamic_text = func(package)
            return str(dynamic_text)
        except Exception as e:
            error_message = f"Addon '{slug}' failed to execute: {e}"
            logger.error(error_message)
            return error_message

    # Fallback to static description if no slug or slug not found
    return addon.description


def collect_addon_blocks(
    identity_disc: Optional['IdentityDisc'],
    iteration_id: Optional[int] = None,
    turn_number: int = 1,
    reasoning_turn_id: Optional[int] = None,
    environment_id: Optional[UUID] = None,
    shift_id: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """
    Returns (addon_name, addon_text) tuples for all addons on the IdentityDisc.

    The Frontal Lobe uses this to inject each Addon as its own user message
    in the Living Chatroom for the current turn.
    """
    if not identity_disc:
        return []

    blocks: List[Tuple[str, str]] = []

    addons = identity_disc.addons.all()
    for addon in addons:
        block_text = _resolve_addon_content(
            addon,
            identity_disc.id,
            identity_disc.id if identity_disc else None,
            iteration_id,
            turn_number,
            reasoning_turn_id,
            environment_id,
            shift_id,
        )
        if block_text:
            blocks.append((addon.name, str(block_text)))

    return blocks


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
    if not identity_disc:
        return 'No Identity mounted. Operating with blank slate.'

    prompt_blocks = [
        render_base_identity(
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
