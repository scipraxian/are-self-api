from typing import List

from frontal_lobe.models import ChatMessage, ChatMessageRole
from identity.addons.addon_package import AddonPackage


def your_move_addon(package: AddonPackage) -> List[ChatMessage]:
    content = (
        'YOUR MOVE:\n'
        '1. You MUST call mcp_internal_monologue ALONGSIDE any other tools you call in parallel. Never fire a tool without also firing your monologue.\n'
        '2. You should call your tools (like `mcp_ticket`) in parallel during the exact same turn.\n'
        '3. Use structured JSON for all tool calls natively.\n'
    )
    return [
        ChatMessage(
            session_id=package.session_id,
            turn_id=package.reasoning_turn_id,
            role_id=ChatMessageRole.USER,
            content=content,
            is_volatile=True,
        )
    ]
