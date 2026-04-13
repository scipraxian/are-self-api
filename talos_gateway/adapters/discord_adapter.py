"""Discord platform adapter; discord.py integration not yet wired."""

import logging
from typing import Any, Awaitable, Callable, Optional

from talos_gateway.adapters.base_patterns import iter_chunked_payloads
from talos_gateway.contracts import DeliveryPayload

logger = logging.getLogger('talos_gateway.adapters.discord')


class DiscordAdapter(object):
    """Discord adapter: conventional API; SDK calls stay isolated here."""

    # Placeholder MAX_MESSAGE_LENGTH
    PLATFORM_NAME = 'discord'
    MAX_MESSAGE_LENGTH = 2000

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self.config = config or {}
        self._on_message: Optional[Callable[[Any], Awaitable[None]]] = None

    async def start(self) -> None:
        """Connect to Discord (stub until discord.py is wired)."""

    async def stop(self) -> None:
        """Disconnect cleanly."""

    async def send(self, payload: DeliveryPayload) -> dict:
        """Deliver a message (stub)."""
        logger.debug('[DiscordAdapter] send channel=%s', payload.channel_id)
        return {
            'success': True,
            'message_id': 'discord-stub',
            'status_code': 200,
        }

    async def send_chunked(self, payload: DeliveryPayload) -> dict:
        """Chunk to ``MAX_MESSAGE_LENGTH`` then send each chunk."""
        last: dict = {'success': False}
        for chunk in iter_chunked_payloads(payload, self.MAX_MESSAGE_LENGTH):
            last = await self.send(chunk)
            if not last.get('success'):
                return last
        return last

    def on_message(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        """Register inbound handler."""
        self._on_message = callback
