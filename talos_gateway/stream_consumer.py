"""Channels WebSocket consumer for gateway streaming.

Inbound text from a local CLI client uses this transport at
``/ws/gateway/stream/`` (see ``talos_gateway.routing``).  The consumer
normalizes JSON into ``PlatformEnvelope`` and forwards to the active
``GatewayOrchestrator``, which wakes reasoning via the canonical
``wake_reasoning`` path.

Connect with ``?session_id=<reasoning_session_uuid>`` to receive LLM token
deltas via ``group_send``, or send a ``join_session`` message after receiving
``inbound_ack`` with a ``session_id``.
"""

import json
import logging
from typing import Any, Optional
from urllib.parse import parse_qs
from uuid import UUID

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from frontal_lobe.channels_streaming import (
    GROUP_PREFIX,
    reasoning_session_group_name,
)
from talos_gateway.gateway import get_active_gateway_orchestrator
from talos_gateway.runtime import handle_interrupt
from talos_gateway.ws_protocol import (
    WS_ERR_INVALID_JSON,
    WS_ERR_NO_GATEWAY,
    WS_ERR_UNKNOWN_TYPE,
    WS_ERR_VALIDATION,
    WS_MSG_ERROR,
    WS_MSG_INBOUND,
    WS_MSG_INBOUND_ACK,
    WS_MSG_INTERRUPT,
    WS_MSG_INTERRUPT_ACK,
    WS_MSG_JOIN_SESSION,
    WS_MSG_JOIN_SESSION_ACK,
    WS_MSG_RESPONSE_COMPLETE,
    WS_MSG_SESSION_STATUS,
    WS_MSG_TOKEN_DELTA,
    platform_envelope_from_inbound_payload,
)

logger = logging.getLogger('talos_gateway.stream_consumer')


def _error_payload(code: str, message: str) -> dict[str, Any]:
    """Build a JSON-serializable WebSocket error frame."""
    return {'type': WS_MSG_ERROR, 'code': code, 'message': message}


class GatewayTokenStreamConsumer(AsyncWebsocketConsumer):
    """JSON channel for inbound CLI messages; outbound LLM token stream (Layer 2)."""

    async def connect(self) -> None:
        """Accept WebSocket; optionally join a ReasoningSession channel group."""
        self._session_group: Optional[str] = None
        raw_qs = self.scope.get('query_string') or b''
        try:
            query_string = raw_qs.decode('utf-8')
        except UnicodeDecodeError:
            query_string = ''
        params = parse_qs(query_string)
        raw_sid = (params.get('session_id') or [None])[0]
        if raw_sid:
            try:
                sid = UUID(str(raw_sid))
            except (ValueError, TypeError):
                logger.warning(
                    '[GatewayTokenStreamConsumer] invalid session_id query: %s',
                    raw_sid,
                )
            else:
                self._session_group = reasoning_session_group_name(sid)
                await self.channel_layer.group_add(
                    self._session_group,
                    self.channel_name,
                )
                logger.debug(
                    '[GatewayTokenStreamConsumer] joined group %s',
                    self._session_group,
                )
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        """Leave session group when subscribed."""
        grp = getattr(self, '_session_group', None)
        if grp:
            await self.channel_layer.group_discard(
                grp,
                self.channel_name,
            )

    # ------------------------------------------------------------------
    # Group message handlers (outbound from reasoning engine)
    # ------------------------------------------------------------------

    async def token_delta(self, event: dict[str, Any]) -> None:
        """Forward a streamed LLM token to the WebSocket (group message handler)."""
        token = event.get('token', '')
        await self.send(
            text_data=json.dumps(
                {'type': WS_MSG_TOKEN_DELTA, 'token': token}
            )
        )

    async def response_complete(self, event: dict[str, Any]) -> None:
        """Forward reasoning completion event to the WebSocket client."""
        await self.send(
            text_data=json.dumps({
                'type': WS_MSG_RESPONSE_COMPLETE,
                'content': event.get('content', ''),
                'session_status': event.get('session_status', ''),
            })
        )

    async def session_status(self, event: dict[str, Any]) -> None:
        """Forward session status change to the WebSocket client."""
        await self.send(
            text_data=json.dumps({
                'type': WS_MSG_SESSION_STATUS,
                'status': event.get('status', ''),
            })
        )

    # ------------------------------------------------------------------
    # Inbound message dispatch
    # ------------------------------------------------------------------

    _SUPPORTED_TYPES = frozenset({
        WS_MSG_INBOUND,
        WS_MSG_JOIN_SESSION,
        WS_MSG_INTERRUPT,
    })

    async def receive(
        self,
        text_data: Optional[str] = None,
        bytes_data: Optional[bytes] = None,
    ) -> None:
        """Dispatch inbound JSON to the active gateway orchestrator."""
        if bytes_data is not None:
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_UNKNOWN_TYPE,
                        'binary frames are not supported',
                    )
                )
            )
            return

        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_INVALID_JSON, 'body is not valid JSON'
                    )
                )
            )
            return

        if not isinstance(data, dict):
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_VALIDATION,
                        'JSON payload must be an object',
                    )
                )
            )
            return

        msg_type = data.get('type')

        if msg_type == WS_MSG_JOIN_SESSION:
            await self._handle_join_session(data)
            return

        if msg_type == WS_MSG_INTERRUPT:
            await self._handle_interrupt()
            return

        if msg_type != WS_MSG_INBOUND:
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_UNKNOWN_TYPE,
                        'unsupported message type: %s' % (msg_type,),
                    )
                )
            )
            return

        orchestrator = get_active_gateway_orchestrator()
        if orchestrator is None:
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_NO_GATEWAY,
                        'gateway orchestrator is not running',
                    )
                )
            )
            return

        try:
            envelope = platform_envelope_from_inbound_payload(data)
        except ValueError as exc:
            await self.send(
                text_data=json.dumps(
                    _error_payload(WS_ERR_VALIDATION, str(exc))
                )
            )
            return

        try:
            result = await orchestrator.handle_inbound(envelope)
        except Exception:
            logger.exception(
                '[GatewayTokenStreamConsumer] handle_inbound failed.'
            )
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_VALIDATION,
                        'inbound handling failed',
                    )
                )
            )
            return

        await self.send(
            text_data=json.dumps({'type': WS_MSG_INBOUND_ACK, 'result': result})
        )

    # ------------------------------------------------------------------
    # Message-type handlers
    # ------------------------------------------------------------------

    async def _handle_join_session(self, data: dict[str, Any]) -> None:
        """Join a reasoning session channel group after connection."""
        raw_sid = data.get('session_id')
        if not raw_sid:
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_VALIDATION,
                        'session_id is required for join_session',
                    )
                )
            )
            return

        try:
            sid = UUID(str(raw_sid))
        except (ValueError, TypeError):
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_VALIDATION,
                        'session_id must be a valid UUID',
                    )
                )
            )
            return

        # Leave previous group if switching sessions.
        if self._session_group:
            await self.channel_layer.group_discard(
                self._session_group,
                self.channel_name,
            )

        self._session_group = reasoning_session_group_name(sid)
        await self.channel_layer.group_add(
            self._session_group,
            self.channel_name,
        )
        logger.debug(
            '[GatewayTokenStreamConsumer] Joined group %s via join_session.',
            self._session_group,
        )
        await self.send(
            text_data=json.dumps({
                'type': WS_MSG_JOIN_SESSION_ACK,
                'session_id': str(sid),
            })
        )

    async def _handle_interrupt(self) -> None:
        """Interrupt the active reasoning session."""
        if not self._session_group:
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_VALIDATION,
                        'no session joined; send join_session first',
                    )
                )
            )
            return

        session_id_str = self._session_group[len(GROUP_PREFIX):]
        try:
            session_id = UUID(session_id_str)
        except (ValueError, TypeError):
            await self.send(
                text_data=json.dumps(
                    _error_payload(
                        WS_ERR_VALIDATION,
                        'could not resolve session from group',
                    )
                )
            )
            return

        result = await sync_to_async(handle_interrupt)(session_id)
        await self.send(
            text_data=json.dumps({
                'type': WS_MSG_INTERRUPT_ACK,
                **result,
            })
        )
