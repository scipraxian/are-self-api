from typing import List

from frontal_lobe.models import ChatMessage
from identity.addons.addon_package import AddonPackage


def normal_chat_addon(package: AddonPackage) -> List[ChatMessage]:
    """
    Identity Addon (Phase: HISTORY):
    Standard chronological chat history. No eviction, no warnings.
    (Note: You could add context window limitation logic here later if you want to truncate.)
    """
    if not package.session_id:
        return []

    return list(
        ChatMessage.objects.filter(
            session_id=package.session_id,
            is_volatile=False
        )
        .select_related('role', 'tool_call__tool')
        .order_by('created')
    )