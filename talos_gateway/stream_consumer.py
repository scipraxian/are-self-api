"""Channels WebSocket consumer for gateway streaming (Layer 4).

Inbound text from a local CLI client uses this transport at
``/ws/gateway/stream/`` (see ``talos_gateway.routing``). Outbound replies for
Phase 1 still go through ``CliAdapter.send`` when wired in later phases; this
consumer only normalizes JSON into ``PlatformEnvelope`` and forwards to the
active ``GatewayOrchestrator``.
"""

import json
import logging
from typing import Any, Optional

from channels.generic.websocket import AsyncWebsocketConsumer

from talos_gateway.gateway import get_active_gateway_orchestrator
from talos_gateway.ws_protocol import (
    WS_ERR_INVALID_JSON,
    WS_ERR_NO_GATEWAY,
    WS_ERR_UNKNOWN_TYPE,
    WS_ERR_VALIDATION,
    WS_MSG_ERROR,
    WS_MSG_INBOUND,
    WS_MSG_INBOUND_ACK,
    platform_envelope_from_inbound_payload,
)

logger = logging.getLogger('talos_gateway.stream_consumer')


def _error_payload(code: str, message: str) -> dict[str, Any]:
    return {'type': WS_MSG_ERROR, 'code': code, 'message': message}


class GatewayTokenStreamConsumer(AsyncWebsocketConsumer):
    """JSON control channel: inbound CLI messages and future Serotonin tokens."""

    async def connect(self) -> None:
        """Accept WebSocket connection."""
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        """Disconnect hook (reserved for logging or cleanup)."""
        _ = close_code

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
                    _error_payload(WS_ERR_INVALID_JSON, 'body is not valid JSON')
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
            logger.exception('[GatewayTokenStreamConsumer] handle_inbound failed.')
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
