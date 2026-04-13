"""WebSocket client for the Are-Self CLI transport."""

import json
import logging
from typing import Any, Callable, Optional
from uuid import uuid4

import websockets

from talos_gateway.ws_protocol import (
    WS_MSG_CREATE_SESSION,
    WS_MSG_ERROR,
    WS_MSG_INBOUND,
    WS_MSG_INTERRUPT,
    WS_MSG_JOIN_SESSION,
    WS_MSG_LIST_SESSIONS,
    WS_MSG_RESPONSE_COMPLETE,
    WS_MSG_SESSION_STATUS,
    WS_MSG_TOKEN_DELTA,
)

logger = logging.getLogger('talos_gateway.cli.client')


class CliClient(object):
    """Async WebSocket client that speaks the gateway stream protocol."""

    def __init__(self, ws_url: str, channel_id: str) -> None:
        self.ws_url = ws_url
        self.channel_id = channel_id
        self._ws: Optional[Any] = None

    async def connect(self) -> None:
        """Establish WebSocket connection to the gateway."""
        self._ws = await websockets.connect(self.ws_url)
        logger.info('[CliClient] Connected to %s.', self.ws_url)

    async def disconnect(self) -> None:
        """Close WebSocket gracefully."""
        if self._ws is not None:
            await self._ws.close()
            logger.info('[CliClient] Disconnected.')

    async def send_message(self, content: str) -> dict:
        """Send an inbound message and return the ack."""
        payload = {
            'type': WS_MSG_INBOUND,
            'channel_id': self.channel_id,
            'message_id': str(uuid4()),
            'content': content,
        }
        await self._ws.send(json.dumps(payload))
        raw = await self._ws.recv()
        return json.loads(raw)

    async def send_interrupt(self) -> dict:
        """Send an interrupt message and return the ack."""
        payload = {'type': WS_MSG_INTERRUPT}
        await self._ws.send(json.dumps(payload))
        raw = await self._ws.recv()
        return json.loads(raw)

    async def send_join_session(self, session_id: str) -> dict:
        """Join a session group and return the ack."""
        payload = {
            'type': WS_MSG_JOIN_SESSION,
            'session_id': session_id,
        }
        await self._ws.send(json.dumps(payload))
        raw = await self._ws.recv()
        return json.loads(raw)

    async def send_list_sessions(self) -> list[dict]:
        """Request and return the list of active sessions."""
        payload = {'type': WS_MSG_LIST_SESSIONS}
        await self._ws.send(json.dumps(payload))
        raw = await self._ws.recv()
        data = json.loads(raw)
        return data.get('sessions', [])

    async def send_create_session(self) -> dict:
        """Create a new session and return the ack with session info."""
        payload = {
            'type': WS_MSG_CREATE_SESSION,
            'channel_id': self.channel_id,
        }
        await self._ws.send(json.dumps(payload))
        raw = await self._ws.recv()
        return json.loads(raw)

    async def listen(
        self,
        on_token: Callable[[str], Any],
        on_complete: Callable[[str, str], Any],
        on_status: Callable[[str], Any],
        on_error: Callable[[str, str], Any],
    ) -> None:
        """Event loop that reads from the WebSocket and dispatches to callbacks."""
        while True:
            raw = await self._ws.recv()
            data = json.loads(raw)
            msg_type = data.get('type', '')

            if msg_type == WS_MSG_TOKEN_DELTA:
                on_token(data.get('token', ''))
            elif msg_type == WS_MSG_RESPONSE_COMPLETE:
                on_complete(
                    data.get('content', ''),
                    data.get('session_status', ''),
                )
            elif msg_type == WS_MSG_SESSION_STATUS:
                on_status(data.get('status', ''))
            elif msg_type == WS_MSG_ERROR:
                on_error(
                    data.get('code', ''),
                    data.get('message', ''),
                )
