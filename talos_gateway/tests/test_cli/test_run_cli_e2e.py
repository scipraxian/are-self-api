"""End-to-end CLI WebSocket round-trip test.

Boots a real ``websockets`` server inside the test process, speaks the
gateway protocol from a fixture handler, connects :class:`CliClient`,
and asserts that both the request/ack correlation and the unsolicited
token-delta path work together. This is the acceptance coverage for
Story 2.1 ("streamed token updates render correctly").

Inline server is intentional: ``WebsocketCommunicator`` exercises the
Channels consumer without a real socket, but the client-side
``websockets.connect`` needs an actual TCP endpoint to verify the
single-dispatcher design under real transport.
"""

import asyncio
import json
from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

import websockets

from talos_gateway.cli.client import CliClient, DisplayCallbacks
from talos_gateway.ws_protocol import (
    WS_MSG_INBOUND,
    WS_MSG_INBOUND_ACK,
    WS_MSG_INTERRUPT,
    WS_MSG_INTERRUPT_ACK,
    WS_MSG_JOIN_SESSION,
    WS_MSG_JOIN_SESSION_ACK,
    WS_MSG_RESPONSE_COMPLETE,
    WS_MSG_TOKEN_DELTA,
)


class _FixtureServer(object):
    """Minimal gateway-protocol server for client-side E2E tests."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.tokens_to_stream: list[str] = []
        self.server: websockets.asyncio.server.Server = None

    async def _handle(self, ws) -> None:
        """Single connection handler speaking the gateway protocol."""
        async for raw in ws:
            data = json.loads(raw)
            self.received.append(data)
            msg_type = data.get('type')
            request_id = data.get('request_id')

            if msg_type == WS_MSG_INBOUND:
                for token in self.tokens_to_stream:
                    await ws.send(json.dumps({
                        'type': WS_MSG_TOKEN_DELTA,
                        'token': token,
                    }))
                ack = {
                    'type': WS_MSG_INBOUND_ACK,
                    'result': {'success': True, 'queue_depth': 1},
                }
                if request_id:
                    ack['request_id'] = request_id
                await ws.send(json.dumps(ack))

                await ws.send(json.dumps({
                    'type': WS_MSG_RESPONSE_COMPLETE,
                    'content': ''.join(self.tokens_to_stream),
                    'session_status': '7',
                }))

            elif msg_type == WS_MSG_JOIN_SESSION:
                ack = {
                    'type': WS_MSG_JOIN_SESSION_ACK,
                    'session_id': data.get('session_id'),
                }
                if request_id:
                    ack['request_id'] = request_id
                await ws.send(json.dumps(ack))

            elif msg_type == WS_MSG_INTERRUPT:
                ack = {
                    'type': WS_MSG_INTERRUPT_ACK,
                    'success': True,
                    'spike_id': 'sp-e2e-1',
                }
                if request_id:
                    ack['request_id'] = request_id
                await ws.send(json.dumps(ack))

    async def start(self) -> int:
        """Bind to an ephemeral port and return it."""
        self.server = await websockets.serve(self._handle, '127.0.0.1', 0)
        return self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Close the listening server and wait for shutdown."""
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()


class CliClientE2EWebSocketTests(SimpleTestCase):
    """E2E round-trip tests against a real ``websockets`` server."""

    def test_message_in_tokens_out_via_websocket(self):
        """Assert send_message returns ack while token_delta routes to on_token."""
        tokens_seen: list[str] = []
        completes: list[tuple[str, str]] = []

        async def _run() -> None:
            server = _FixtureServer()
            server.tokens_to_stream = ['hello', ' ', 'world']
            port = await server.start()
            try:
                client = CliClient(
                    'ws://127.0.0.1:%s' % port, 'chan-e2e'
                )
                callbacks = DisplayCallbacks(
                    on_token=lambda t: tokens_seen.append(t),
                    on_complete=lambda c, s: completes.append((c, s)),
                    on_status=lambda s: None,
                    on_error=lambda c, m: None,
                )
                await client.start(callbacks)
                try:
                    ack = await client.send_message('drive the reasoner')
                    self.assertEqual(ack['type'], WS_MSG_INBOUND_ACK)
                    self.assertTrue(ack['result']['success'])
                    await asyncio.sleep(0.05)
                finally:
                    await client.stop()
            finally:
                await server.stop()

        async_to_sync(_run)()

        self.assertEqual(tokens_seen, ['hello', ' ', 'world'])
        self.assertEqual(len(completes), 1)
        self.assertEqual(completes[0][0], 'hello world')

    def test_interrupt_flow_end_to_end(self):
        """Assert send_interrupt resolves with the matching interrupt_ack."""

        async def _run() -> dict:
            server = _FixtureServer()
            port = await server.start()
            try:
                client = CliClient(
                    'ws://127.0.0.1:%s' % port, 'chan-e2e-int'
                )
                callbacks = DisplayCallbacks(
                    on_token=lambda t: None,
                    on_complete=lambda c, s: None,
                    on_status=lambda s: None,
                    on_error=lambda c, m: None,
                )
                await client.start(callbacks)
                try:
                    await client.send_join_session(
                        '11111111-1111-1111-1111-111111111111'
                    )
                    return await client.send_interrupt()
                finally:
                    await client.stop()
            finally:
                await server.stop()

        ack = async_to_sync(_run)()
        self.assertEqual(ack['type'], WS_MSG_INTERRUPT_ACK)
        self.assertTrue(ack['success'])
        self.assertEqual(ack['spike_id'], 'sp-e2e-1')
