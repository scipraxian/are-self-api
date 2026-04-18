"""WebSocket client for the Are-Self CLI transport.

The client owns exactly one reader coroutine. Inbound frames split by type:
``*_ack`` frames resolve per-request :class:`asyncio.Future` objects keyed by
``request_id``; unsolicited frames (``token_delta``, ``response_complete``,
``session_status``, ``error``) route to :class:`DisplayCallbacks`.

Request methods (``send_message``, ``send_interrupt``, ...) never call
``ws.recv()``; they await the pending future that the reader resolves. This
is the fix for the concurrent-recv race that the naive
"listen-loop plus per-request recv" pattern would trigger on the real
``websockets`` library.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import uuid4

import websockets
from websockets.exceptions import ConnectionClosed

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


@dataclass
class DisplayCallbacks(object):
    """Callbacks invoked by the reader loop for unsolicited server frames.

    All callbacks are plain (sync) callables. They are expected to be fast,
    side-effect-only functions such as writing a token to stdout.
    """

    on_token: Callable[[str], Any]
    on_complete: Callable[[str, str], Any]
    on_status: Callable[[str], Any]
    on_error: Callable[[str, str], Any]


class CliClient(object):
    """Async WebSocket client speaking the gateway stream protocol."""

    def __init__(
        self,
        ws_url: str,
        channel_id: str,
        identity_disc_id: Optional[str] = None,
    ) -> None:
        self.ws_url = ws_url
        self.channel_id = channel_id
        self.identity_disc_id = identity_disc_id
        self._ws: Optional[Any] = None
        self._pending: dict[str, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._callbacks: Optional[DisplayCallbacks] = None
        self._stopping = False

    async def start(self, callbacks: DisplayCallbacks) -> None:
        """Connect and spawn the reader task that owns ``ws.recv()``."""
        self._callbacks = callbacks
        self._ws = await websockets.connect(self.ws_url)
        self._reader_task = asyncio.create_task(self._reader_loop())
        logger.info('[CliClient] Connected to %s.', self.ws_url)

    async def stop(self) -> None:
        """Cancel reader, fail pending requests, and close the socket."""
        if self._stopping:
            return
        self._stopping = True

        reader = self._reader_task
        if reader is not None and not reader.done():
            reader.cancel()
            try:
                await reader
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.debug(
                    '[CliClient] Reader exited with exception: %s.', exc
                )

        self._fail_pending(ConnectionClosed(None, None))

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as exc:
                logger.debug(
                    '[CliClient] WebSocket close raised: %s.', exc
                )
        logger.info('[CliClient] Disconnected.')

    async def send_message(self, content: str) -> dict:
        """Send an inbound message and return the matching ``inbound_ack``."""
        payload: dict[str, Any] = {
            'type': WS_MSG_INBOUND,
            'channel_id': self.channel_id,
            'message_id': str(uuid4()),
            'content': content,
        }
        if self.identity_disc_id:
            payload['identity_disc_id'] = self.identity_disc_id
        return await self._request(payload)

    async def send_interrupt(self) -> dict:
        """Send an interrupt message and return the matching ``interrupt_ack``."""
        return await self._request({'type': WS_MSG_INTERRUPT})

    async def send_join_session(self, session_id: str) -> dict:
        """Join a session group and return the matching ``join_session_ack``."""
        return await self._request({
            'type': WS_MSG_JOIN_SESSION,
            'session_id': session_id,
        })

    async def send_list_sessions(self) -> list[dict]:
        """Request active sessions and return the ``sessions`` list."""
        ack = await self._request({'type': WS_MSG_LIST_SESSIONS})
        return ack.get('sessions', [])

    async def send_create_session(self) -> dict:
        """Create a session and return the matching ``create_session_ack``."""
        return await self._request({
            'type': WS_MSG_CREATE_SESSION,
            'channel_id': self.channel_id,
        })

    async def _request(self, payload: dict[str, Any]) -> dict:
        """Send a request frame with a fresh ``request_id`` and await the ack."""
        if self._ws is None:
            raise ConnectionClosed(None, None)
        request_id = str(uuid4())
        payload['request_id'] = request_id
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._ws.send(json.dumps(payload))
        except Exception:
            self._pending.pop(request_id, None)
            raise
        return await future

    async def _reader_loop(self) -> None:
        """Single owner of ``ws.recv()``. Dispatches by ``request_id`` or type."""
        try:
            while True:
                raw = await self._ws.recv()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(
                        '[CliClient] Dropping non-JSON frame: %s.', raw
                    )
                    continue
                if not isinstance(data, dict):
                    logger.warning(
                        '[CliClient] Dropping non-object frame: %s.', data
                    )
                    continue
                self._dispatch(data)
        except asyncio.CancelledError:
            raise
        except ConnectionClosed as exc:
            logger.info('[CliClient] Reader saw connection close: %s.', exc)
            self._fail_pending(exc)
        except Exception as exc:
            logger.exception(
                '[CliClient] Reader crashed: %s.', exc
            )
            self._fail_pending(exc)

    def _dispatch(self, data: dict[str, Any]) -> None:
        """Route one parsed frame to either a pending future or display path."""
        request_id = data.get('request_id')
        if isinstance(request_id, str) and request_id:
            future = self._pending.pop(request_id, None)
            if future is not None and not future.done():
                future.set_result(data)
                return
            if future is None:
                logger.debug(
                    '[CliClient] Ack for unknown request_id %s dropped.',
                    request_id,
                )
                return

        msg_type = data.get('type', '')
        if self._callbacks is None:
            return

        if msg_type == WS_MSG_TOKEN_DELTA:
            self._callbacks.on_token(data.get('token', ''))
        elif msg_type == WS_MSG_RESPONSE_COMPLETE:
            self._callbacks.on_complete(
                data.get('content', ''),
                data.get('session_status', ''),
            )
        elif msg_type == WS_MSG_SESSION_STATUS:
            self._callbacks.on_status(data.get('status', ''))
        elif msg_type == WS_MSG_ERROR:
            self._callbacks.on_error(
                data.get('code', ''),
                data.get('message', ''),
            )
        else:
            logger.debug(
                '[CliClient] Ignoring unsolicited frame type %s.', msg_type
            )

    def _fail_pending(self, exc: BaseException) -> None:
        """Resolve all pending futures with an exception (stop / close)."""
        pending = self._pending
        self._pending = {}
        for future in pending.values():
            if not future.done():
                future.set_exception(exc)
