from typing import List

from frontal_lobe.models import ChatMessage, ChatMessageRole, ReasoningTurn
from identity.addons.addon_package import AddonPackage


def deadline_addon(package: AddonPackage) -> List[ChatMessage]:
    if not package.reasoning_turn_id:
        return [
            ChatMessage(
                session_id=package.session_id,
                turn_id=package.reasoning_turn_id,
                role_id=ChatMessageRole.USER,
                content='Deadline Addon Preview Mode (No Reasoning Turn)',
                is_volatile=True,
            )
        ]
    session = ReasoningTurn.objects.get(id=package.reasoning_turn_id).session

    current_turn = package.turn_number
    max_turns = session.max_turns
    remaining_turns = max_turns - current_turn
    progress = current_turn / max_turns

    prompt_blocks = []

    percentage_remaining = round(progress * 100, 0)

    status = ''
    if remaining_turns == 1:
        status = 'CRITICAL:'
    elif remaining_turns <= 5:
        status = 'WARNING:'
    prompt_blocks.append(
        f'{status}{remaining_turns} of {max_turns} '
        f'TURNS REMAIN ({percentage_remaining}%).\n'
    )
    if remaining_turns == 1:
        prompt_blocks.append(
            '[LAST TURN. SUBMIT mcp_done or session will be DESTROYED.]'
        )
    elif remaining_turns <= 5:
        prompt_blocks.append(
            f'[CRITICAL: ONLY {remaining_turns} TURNS REMAIN.]'
        )

    text_content = '\n\n'.join(prompt_blocks)
    return [
        ChatMessage(
            session_id=package.session_id,
            turn_id=package.reasoning_turn_id,
            role_id=ChatMessageRole.USER,
            content=text_content,
            is_volatile=True,
        )
    ]
