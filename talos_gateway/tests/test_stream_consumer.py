"""Tests for talos_gateway.stream_consumer."""

import asyncio
import inspect
import json

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, override_settings
from django.urls import path

from common.tests.common_test_case import CommonFixturesAPITestCase
from talos_gateway.contracts import PlatformEnvelope
from talos_gateway.gateway import (
    GatewayOrchestrator,
    clear_active_gateway_orchestrator,
    set_active_gateway_orchestrator,
)
from talos_gateway.stream_consumer import GatewayTokenStreamConsumer
from talos_gateway.ws_protocol import (
    WS_ERR_INVALID_JSON,
    WS_ERR_NO_GATEWAY,
    WS_ERR_UNKNOWN_TYPE,
    WS_ERR_VALIDATION,
    WS_MSG_INBOUND,
    WS_MSG_INBOUND_ACK,
)

THALAMUS_DISC_PK = '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838'


def _gateway_application():
    return URLRouter(
        [
            path(
                'ws/gateway/stream/',
                GatewayTokenStreamConsumer.as_asgi(),
            ),
        ]
    )


async def _ws_connect_send_receive(payload: str) -> dict:
    communicator = WebsocketCommunicator(
        _gateway_application(),
        '/ws/gateway/stream/',
    )
    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_to(text_data=payload)
    raw = await communicator.receive_from()
    await communicator.disconnect()
    return json.loads(raw)


class _RecordingOrchestrator(object):
    """Minimal stand-in with async ``handle_inbound``."""

    def __init__(self) -> None:
        self.calls: list[PlatformEnvelope] = []

    async def handle_inbound(self, envelope: PlatformEnvelope) -> dict:
        self.calls.append(envelope)
        return {'success': True, 'queue_depth': 1}


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
    }
)
class GatewayTokenStreamConsumerTests(SimpleTestCase):
    """WebSocket tests using in-memory channel layer."""

    def tearDown(self) -> None:
        clear_active_gateway_orchestrator()
        super().tearDown()

    def test_inbound_dispatches_to_orchestrator(self):
        """Assert inbound JSON invokes handle_inbound with expected envelope."""
        orch = _RecordingOrchestrator()
        set_active_gateway_orchestrator(orch)

        async def _run() -> None:
            body = json.dumps(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'chan-ws-1',
                    'message_id': 'm-ws-1',
                    'content': 'hello from ws',
                    'sender_id': 'user-a',
                    'sender_name': 'User A',
                }
            )
            data = await _ws_connect_send_receive(body)
            self.assertEqual(data['type'], WS_MSG_INBOUND_ACK)
            self.assertTrue(data['result'].get('success'))
            self.assertEqual(len(orch.calls), 1)
            env = orch.calls[0]
            self.assertEqual(env.platform, 'cli')
            self.assertEqual(env.channel_id, 'chan-ws-1')
            self.assertEqual(env.message_id, 'm-ws-1')
            self.assertEqual(env.content, 'hello from ws')
            self.assertEqual(env.sender_id, 'user-a')
            self.assertEqual(env.sender_name, 'User A')

        asyncio.run(_run())

    def test_no_orchestrator_returns_error(self):
        """Assert missing active orchestrator yields gateway_unavailable."""
        clear_active_gateway_orchestrator()

        async def _run() -> None:
            body = json.dumps(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'c',
                    'message_id': '1',
                    'content': 'x',
                }
            )
            data = await _ws_connect_send_receive(body)
            self.assertEqual(data['type'], 'error')
            self.assertEqual(data['code'], WS_ERR_NO_GATEWAY)

        asyncio.run(_run())

    def test_invalid_json_returns_error(self):
        """Assert non-JSON text yields invalid_json."""
        set_active_gateway_orchestrator(_RecordingOrchestrator())

        async def _run() -> None:
            data = await _ws_connect_send_receive('not-json')
            self.assertEqual(data['type'], 'error')
            self.assertEqual(data['code'], WS_ERR_INVALID_JSON)

        asyncio.run(_run())

    def test_unknown_message_type_returns_error(self):
        """Assert non-inbound type yields unknown_message_type."""
        set_active_gateway_orchestrator(_RecordingOrchestrator())

        async def _run() -> None:
            data = await _ws_connect_send_receive('{"type":"ping"}')
            self.assertEqual(data['type'], 'error')
            self.assertEqual(data['code'], WS_ERR_UNKNOWN_TYPE)

        asyncio.run(_run())

    def test_validation_error_on_missing_channel_id(self):
        """Assert validation_error when channel_id is missing."""
        set_active_gateway_orchestrator(_RecordingOrchestrator())

        async def _run() -> None:
            body = json.dumps(
                {
                    'type': WS_MSG_INBOUND,
                    'message_id': '1',
                    'content': 'x',
                }
            )
            data = await _ws_connect_send_receive(body)
            self.assertEqual(data['type'], 'error')
            self.assertEqual(data['code'], WS_ERR_VALIDATION)

        asyncio.run(_run())

    def test_phase1_gateway_modules_avoid_reasoning_engine_hooks(self):
        """Assert Phase 1 gateway code omits FrontalLobe.run and fire_spike."""
        import talos_gateway.gateway as gw_mod
        import talos_gateway.message_router as mr_mod
        import talos_gateway.stream_consumer as sc_mod

        for module in (gw_mod, mr_mod, sc_mod):
            source = inspect.getsource(module)
            self.assertNotIn('FrontalLobe', source)
            self.assertNotIn('fire_spike', source)

    def test_handle_inbound_exception_returns_error(self):
        """Assert orchestrator failures surface as validation error frame."""

        class BrokenOrchestrator(object):
            async def handle_inbound(self, _envelope):
                raise RuntimeError('simulated failure')

        set_active_gateway_orchestrator(BrokenOrchestrator())

        async def _run() -> None:
            body = json.dumps(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'c',
                    'message_id': '1',
                    'content': 'x',
                }
            )
            data = await _ws_connect_send_receive(body)
            self.assertEqual(data['type'], 'error')
            self.assertEqual(data['code'], WS_ERR_VALIDATION)

        asyncio.run(_run())


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
    },
    TALOS_GATEWAY={
        'platforms': {'cli': {'enabled': True}},
        'default_identity_disc': THALAMUS_DISC_PK,
        'session_timeout_minutes': 60,
    },
)
class GatewayStreamConsumerIntegrationTests(CommonFixturesAPITestCase):
    """WebSocket path updates ``ReasoningSession.swarm_message_queue``."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    def tearDown(self) -> None:
        clear_active_gateway_orchestrator()
        super().tearDown()

    def test_inbound_websocket_queues_on_reasoning_session(self):
        """Assert full path persists queued message on the reasoning session."""
        orch = GatewayOrchestrator()
        orch.load_adapters()
        set_active_gateway_orchestrator(orch)

        async def _run() -> None:
            body = json.dumps(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'chan-int-ws',
                    'message_id': 'mid-int',
                    'content': 'integration hello',
                }
            )
            data = await _ws_connect_send_receive(body)
            self.assertEqual(data['type'], WS_MSG_INBOUND_ACK)
            self.assertTrue(data['result'].get('success'))

        asyncio.run(_run())

        from frontal_lobe.models import ReasoningSession

        rs = ReasoningSession.objects.get(
            gateway_sessions__platform='cli',
            gateway_sessions__channel_id='chan-int-ws',
        )
        self.assertEqual(len(rs.swarm_message_queue), 1)
        self.assertEqual(
            rs.swarm_message_queue[0]['content'], 'integration hello'
        )
