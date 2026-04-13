"""Identity addon: platform-specific guidance from the active GatewaySession."""

import logging
from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn
from talos_gateway.models import GatewaySession

logger = logging.getLogger(__name__)

PLATFORM_HINTS = {
    'discord': """
## Platform: Discord
- User messages may include attachments, voice audio, and replies.
- Use media delivery for images and audio files (reference with MEDIA: path).
- Responses over 2000 characters will be auto-chunked.
- Voice responses are supported — generate voice if the user sends voice.
""".strip(),
    'telegram': """
## Platform: Telegram
- MarkdownV2 formatting is required. Escape: _, *, [, ], (, ), ~, `, >, #, +, -, =, |, {, }, ., !
- Code blocks use triple backticks with language tag.
- Max message length: 4096 characters.
""".strip(),
    'cli': """
## Platform: CLI (Terminal)
- Full-length responses are fine (no character limit).
- Code blocks render natively. Markdown and ANSI colors supported.
- Interactive file path completion is available.
""".strip(),
}


def platform_hint_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: CONTEXT).

    Resolves ``platform`` from ``GatewaySession`` for this reasoning session.
    Unknown or missing platform yields no message.
    """
    if not turn or not turn.session:
        return []

    try:
        gs = (
            GatewaySession.objects.filter(reasoning_session=turn.session)
            .only('platform')
            .first()
        )
    except Exception as exc:
        logger.warning('[platform_hint_addon] Gateway lookup failed: %s', exc)
        return []

    if not gs or not gs.platform:
        return []

    hint = PLATFORM_HINTS.get(gs.platform.strip().lower())
    if not hint:
        return []

    return [{'role': 'system', 'content': hint}]
