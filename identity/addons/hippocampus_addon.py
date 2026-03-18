from typing import List

from asgiref.sync import sync_to_async

from central_nervous_system.models import Spike
from frontal_lobe.models import ChatMessage, ChatMessageRole, ReasoningSession
from hippocampus.hippocampus import TalosHippocampus
from identity.addons.addon_package import AddonPackage


async def hippocampus_addon(package: AddonPackage) -> List[ChatMessage]:
    """
    Identity Addon (Phase: CONTEXT)
    Retrieves the memory catalog and active engrams for the current turn.
    """
    if not package.session_id or not package.spike_id:
        return []

    current_turn = package.turn_number

    if current_turn == 1:
        spike = await sync_to_async(Spike.objects.get)(id=package.spike_id)
        catalog_block = await TalosHippocampus.get_turn_1_catalog(spike)
    else:
        session = await sync_to_async(ReasoningSession.objects.get)(
            id=package.session_id
        )
        catalog_block = await TalosHippocampus.get_recent_catalog(session)

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
