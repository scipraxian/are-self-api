from typing import List

from frontal_lobe.models import ChatMessage, ChatMessageRole
from identity.addons.addon_package import AddonPackage
from identity.models import IdentityDisc


def identity_info_addon(package: AddonPackage) -> List[ChatMessage]:
    """
    Identity Addon (Phase: IDENTIFY)
    Injects the core system prompt, persona, and environmental rules.
    STRICTLY SYNCHRONOUS.
    """
    # it forced a local import.
    from identity.identity_prompt import build_identity_prompt

    if not package.identity_disc or not package.reasoning_turn_id:
        return []

    # Fetch the actual Disc object for the prompt builder
    disc = IdentityDisc.objects.get(id=package.identity_disc)

    # Everything you used to get from `self` and `turn_record`
    # is perfectly cached inside `package`!
    prompt_text = build_identity_prompt(
        identity_disc=disc,
        iteration_id=package.iteration,
        turn_number=package.turn_number,
        reasoning_turn_id=package.reasoning_turn_id,
    )

    if not prompt_text:
        return []

    return [
        ChatMessage(
            session_id=package.session_id,
            turn_id=package.reasoning_turn_id,
            role_id=ChatMessageRole.SYSTEM,  # Core Identity is usually SYSTEM
            content=prompt_text,
            is_volatile=True,
        )
    ]
