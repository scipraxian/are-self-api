"""Channels WebSocket consumer for gateway streaming (Layer 4)."""

import json
import logging
from typing import Optional

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger('talos_gateway.stream_consumer')


class GatewayTokenStreamConsumer(AsyncWebsocketConsumer):
    """Accepts JSON token/control messages from gateway clients (e.g. CLI)."""

    async def connect(self) -> None:
        """Accept WebSocket connection."""
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        """Log disconnect."""
        _ = close_code

    async def receive(
        self,
        text_data: Optional[str] = None,
        bytes_data: Optional[bytes] = None,
    ) -> None:
        """Echo structured JSON for protocol tests; extend for Serotonin routing."""
        if text_data:
            try:
                data = json.loads(text_data)
            except json.JSONDecodeError:
                data = {'raw': text_data}
            await self.send(
                text_data=json.dumps({'type': 'echo', 'payload': data})
            )
