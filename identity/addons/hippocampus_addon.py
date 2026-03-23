from typing import List

from central_nervous_system.models import Spike
from frontal_lobe.models import ChatMessage, ChatMessageRole, ReasoningSession
from hippocampus.hippocampus import TalosHippocampus
from identity.addons.addon_package import AddonPackage


def hippocampus_addon(package: AddonPackage) -> List[ChatMessage]:
    """
    Identity Addon (Phase: CONTEXT)
    Retrieves the memory catalog and active engrams for the current turn.
    STRICTLY SYNCHRONOUS.
    """
    if not package.session_id or not package.spike_id:
        return []

    current_turn = package.turn_number

    # Execute the Hippocampus memory retrieval natively
    # (These methods are now purely synchronous in TalosHippocampus)
    if current_turn == 1:
        spike = Spike.objects.get(id=package.spike_id)
        catalog_block = TalosHippocampus.get_turn_1_catalog(spike)
    else:
        session = ReasoningSession.objects.get(id=package.session_id)
        catalog_block = TalosHippocampus.get_recent_catalog(session)

    if not catalog_block:
        return []

    return [
        ChatMessage(
            session_id=package.session_id,
            turn_id=package.reasoning_turn_id,
            role_id=ChatMessageRole.USER,
            content=catalog_block,
            is_volatile=True,
        )
    ]
