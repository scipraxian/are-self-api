"""Tests for talos_gateway.stream_consumer."""

import asyncio
import inspect
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, TransactionTestCase, override_settings
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
    WS_MSG_CREATE_SESSION,
    WS_MSG_CREATE_SESSION_ACK,
    WS_MSG_INBOUND,
    WS_MSG_INBOUND_ACK,
    WS_MSG_INTERRUPT,
    WS_MSG_INTERRUPT_ACK,
    WS_MSG_JOIN_SESSION,
    WS_MSG_JOIN_SESSION_ACK,
    WS_MSG_LIST_SESSIONS,
    WS_MSG_LIST_SESSIONS_ACK,
    WS_MSG_RESPONSE_COMPLETE,
    WS_MSG_SESSION_STATUS,
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

    databases = '__all__'

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

    def test_transport_modules_avoid_direct_reasoning_hooks(self):
        """Assert transport modules do not directly import FrontalLobe or fire_spike.

        The ``runtime`` module is the canonical bridge and may reference these.
        Transport modules (gateway orchestrator and stream consumer) must not.
        """
        import talos_gateway.gateway as gw_mod
        import talos_gateway.stream_consumer as sc_mod

        for module in (gw_mod, sc_mod):
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


_EMBED_PATCH = patch(
    'frontal_lobe.synapse.OllamaClient.embed', return_value=None
)


def _noop_async_to_sync(fn):
    """No-op replacement for async_to_sync used in signal handlers.

    Django post_save signal handlers broadcast via async_to_sync which
    raises when called from inside a running event loop (asyncio.run /
    Channels consumers). This wrapper silently drops the call so the
    test can exercise the async consumer path without signal side-effects.
    """
    def wrapper(*args, **kwargs):
        pass
    return wrapper


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
class GatewayStreamConsumerIntegrationTests(TransactionTestCase):
    """WebSocket integration path — TransactionTestCase required.

    The Channels consumer runs ORM queries inside asyncio.run() which
    may obtain a different DB connection. TransactionTestCase commits
    fixtures so all connections can read them.
    """

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    @classmethod
    def setUpClass(cls):
        _EMBED_PATCH.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        _EMBED_PATCH.stop()

    def tearDown(self) -> None:
        clear_active_gateway_orchestrator()
        super().tearDown()

    @patch('thalamus.thalamus.fire_spike')
    @patch('thalamus.signals.async_to_sync', _noop_async_to_sync)
    @patch('talos_gateway.signals.async_to_sync', _noop_async_to_sync)
    @patch('asgiref.sync.async_to_sync', _noop_async_to_sync)
    def test_inbound_websocket_queues_on_reasoning_session(self, _mock_fire):
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


# ------------------------------------------------------------------
# Story 1.3 — Group message handler tests
# ------------------------------------------------------------------


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
    }
)
class GatewayGroupMessageHandlerTests(SimpleTestCase):
    """Assert group_send events are forwarded to the WebSocket client."""

    databases = '__all__'

    def test_response_complete_forwarded_to_websocket(self):
        """Assert response_complete group event reaches WebSocket client."""
        from channels.layers import get_channel_layer

        async def _run() -> None:
            sid = str(uuid4())
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_to(
                text_data=json.dumps({
                    'type': WS_MSG_JOIN_SESSION,
                    'session_id': sid,
                })
            )
            join_raw = await communicator.receive_from()
            join_data = json.loads(join_raw)
            self.assertEqual(join_data['type'], WS_MSG_JOIN_SESSION_ACK)

            layer = get_channel_layer()
            group = 'session_%s' % sid
            await layer.group_send(group, {
                'type': 'response_complete',
                'content': 'Here is my answer.',
                'session_status': '7',
            })

            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], WS_MSG_RESPONSE_COMPLETE)
            self.assertEqual(data['content'], 'Here is my answer.')
            self.assertEqual(data['session_status'], '7')
            await communicator.disconnect()

        asyncio.run(_run())

    def test_session_status_forwarded_to_websocket(self):
        """Assert session_status group event reaches WebSocket client."""
        from channels.layers import get_channel_layer

        async def _run() -> None:
            sid = str(uuid4())
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_to(
                text_data=json.dumps({
                    'type': WS_MSG_JOIN_SESSION,
                    'session_id': sid,
                })
            )
            join_raw = await communicator.receive_from()
            join_data = json.loads(join_raw)
            self.assertEqual(join_data['type'], WS_MSG_JOIN_SESSION_ACK)

            layer = get_channel_layer()
            group = 'session_%s' % sid
            await layer.group_send(group, {
                'type': 'session_status',
                'status': 'COMPLETED',
            })

            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], WS_MSG_SESSION_STATUS)
            self.assertEqual(data['status'], 'COMPLETED')
            await communicator.disconnect()

        asyncio.run(_run())


# ------------------------------------------------------------------
# Story 1.3 — Signal broadcast tests
# ------------------------------------------------------------------


THALAMUS_DISC_PK_SIGNAL = '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838'


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
    },
    TALOS_GATEWAY={
        'default_identity_disc': THALAMUS_DISC_PK,
        'session_timeout_minutes': 60,
    },
)
class GatewaySignalBroadcastTests(CommonFixturesAPITestCase):
    """Assert post_save signal broadcasts response_complete on status change."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    @patch('talos_gateway.signals.get_channel_layer')
    def test_signal_broadcasts_on_attention_required(self, mock_get_layer):
        """Assert post_save broadcasts when session moves to ATTENTION_REQUIRED."""
        from frontal_lobe.models import ReasoningSession, ReasoningStatusID

        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        session = ReasoningSession.objects.create(
            identity_disc_id=THALAMUS_DISC_PK_SIGNAL,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=50,
        )

        session.status_id = ReasoningStatusID.ATTENTION_REQUIRED
        session.save(update_fields=['status_id'])

        mock_layer.group_send.assert_called()
        call_args = mock_layer.group_send.call_args
        group_name = call_args[0][0]
        event = call_args[0][1]
        self.assertIn(str(session.pk), group_name)
        self.assertEqual(event['type'], 'response_complete')

    @patch('talos_gateway.signals.get_channel_layer')
    def test_signal_broadcasts_on_completed(self, mock_get_layer):
        """Assert post_save broadcasts when session moves to COMPLETED."""
        from frontal_lobe.models import ReasoningSession, ReasoningStatusID

        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        session = ReasoningSession.objects.create(
            identity_disc_id=THALAMUS_DISC_PK_SIGNAL,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=50,
        )

        session.status_id = ReasoningStatusID.COMPLETED
        session.save(update_fields=['status_id'])

        mock_layer.group_send.assert_called()
        event = mock_layer.group_send.call_args[0][1]
        self.assertEqual(event['type'], 'response_complete')
        self.assertEqual(event['session_status'], str(ReasoningStatusID.COMPLETED))

    @patch('talos_gateway.signals.get_channel_layer')
    def test_signal_skips_non_broadcast_status(self, mock_get_layer):
        """Assert post_save does NOT broadcast for ACTIVE status."""
        from frontal_lobe.models import ReasoningSession, ReasoningStatusID

        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        session = ReasoningSession.objects.create(
            identity_disc_id=THALAMUS_DISC_PK_SIGNAL,
            status_id=ReasoningStatusID.PENDING,
            max_turns=50,
        )

        session.status_id = ReasoningStatusID.ACTIVE
        session.save(update_fields=['status_id'])

        mock_layer.group_send.assert_not_called()


# ------------------------------------------------------------------
# Story 1.4 — WebSocket-level interrupt tests
# ------------------------------------------------------------------


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
    }
)
class GatewayInterruptWebSocketTests(SimpleTestCase):
    """WebSocket-level tests for the interrupt message type."""

    databases = '__all__'

    def test_interrupt_without_session_returns_error(self):
        """Assert interrupt before join_session yields validation error."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_to(
                text_data=json.dumps({'type': WS_MSG_INTERRUPT})
            )
            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], 'error')
            self.assertEqual(data['code'], WS_ERR_VALIDATION)
            self.assertIn('no session joined', data['message'])
            await communicator.disconnect()

        asyncio.run(_run())

    def test_join_session_then_interrupt_returns_ack(self):
        """Assert interrupt after join_session calls handle_interrupt and returns ack."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            session_id = str(uuid4())

            await communicator.send_to(
                text_data=json.dumps({
                    'type': WS_MSG_JOIN_SESSION,
                    'session_id': session_id,
                })
            )
            raw_join = await communicator.receive_from()
            join_data = json.loads(raw_join)
            self.assertEqual(join_data['type'], WS_MSG_JOIN_SESSION_ACK)

            with patch(
                'talos_gateway.stream_consumer.handle_interrupt',
                return_value={'success': True, 'spike_id': str(uuid4())},
            ):
                await communicator.send_to(
                    text_data=json.dumps({'type': WS_MSG_INTERRUPT})
                )
                raw_int = await communicator.receive_from()
                int_data = json.loads(raw_int)
                self.assertEqual(int_data['type'], WS_MSG_INTERRUPT_ACK)
                self.assertTrue(int_data['success'])

            await communicator.disconnect()

        asyncio.run(_run())

    def test_join_session_ack_contains_session_id(self):
        """Assert join_session response includes the session_id."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            sid = str(uuid4())
            await communicator.send_to(
                text_data=json.dumps({
                    'type': WS_MSG_JOIN_SESSION,
                    'session_id': sid,
                })
            )
            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], WS_MSG_JOIN_SESSION_ACK)
            self.assertEqual(data['session_id'], sid)
            await communicator.disconnect()

        asyncio.run(_run())

    def test_join_session_invalid_uuid_returns_error(self):
        """Assert join_session with invalid UUID returns validation error."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_to(
                text_data=json.dumps({
                    'type': WS_MSG_JOIN_SESSION,
                    'session_id': 'not-a-uuid',
                })
            )
            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], 'error')
            self.assertEqual(data['code'], WS_ERR_VALIDATION)
            await communicator.disconnect()

        asyncio.run(_run())


# ------------------------------------------------------------------
# Story 2.1 — Session management WebSocket message tests
# ------------------------------------------------------------------


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
class GatewaySessionManagementWebSocketTests(TransactionTestCase):
    """WebSocket tests for list_sessions and create_session message types."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    @classmethod
    def setUpClass(cls):
        _EMBED_PATCH.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        _EMBED_PATCH.stop()

    def tearDown(self) -> None:
        clear_active_gateway_orchestrator()
        super().tearDown()

    @patch('thalamus.signals.async_to_sync', _noop_async_to_sync)
    @patch('talos_gateway.signals.async_to_sync', _noop_async_to_sync)
    @patch('asgiref.sync.async_to_sync', _noop_async_to_sync)
    def test_list_sessions_returns_ack_with_sessions(self, *_mocks):
        """Assert list_sessions message returns list_sessions_ack with session data."""
        from talos_gateway.session_manager import SessionManager

        sm = SessionManager()
        _gs, rs = sm.create_session('cli', 'chan-ws-list')

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_to(
                text_data=json.dumps({'type': WS_MSG_LIST_SESSIONS})
            )
            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], WS_MSG_LIST_SESSIONS_ACK)
            self.assertIsInstance(data['sessions'], list)
            self.assertGreaterEqual(len(data['sessions']), 1)
            found = [s for s in data['sessions'] if s['session_id'] == str(rs.pk)]
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]['channel_id'], 'chan-ws-list')
            await communicator.disconnect()

        asyncio.run(_run())

    @patch('thalamus.signals.async_to_sync', _noop_async_to_sync)
    @patch('talos_gateway.signals.async_to_sync', _noop_async_to_sync)
    @patch('asgiref.sync.async_to_sync', _noop_async_to_sync)
    def test_create_session_returns_ack_and_joins_group(self, *_mocks):
        """Assert create_session returns session_id and auto-joins the channels group."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_to(
                text_data=json.dumps({
                    'type': WS_MSG_CREATE_SESSION,
                    'channel_id': 'chan-ws-create',
                })
            )
            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], WS_MSG_CREATE_SESSION_ACK)
            self.assertIn('session_id', data)
            self.assertIn('channel_id', data)
            self.assertEqual(data['channel_id'], 'chan-ws-create')

            session_id = data['session_id']
            from channels.layers import get_channel_layer

            layer = get_channel_layer()
            group = 'session_%s' % session_id
            await layer.group_send(group, {
                'type': 'response_complete',
                'content': 'auto-joined test',
                'session_status': '1',
            })

            raw2 = await communicator.receive_from()
            data2 = json.loads(raw2)
            self.assertEqual(data2['type'], WS_MSG_RESPONSE_COMPLETE)
            self.assertEqual(data2['content'], 'auto-joined test')
            await communicator.disconnect()

        asyncio.run(_run())


# ------------------------------------------------------------------
# Epic 2 revision — request_id echo contract
# ------------------------------------------------------------------


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
class GatewayRequestIdEchoTests(TransactionTestCase):
    """Assert every ``*_ack`` frame echoes ``request_id`` when the client sends it."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    @classmethod
    def setUpClass(cls):
        _EMBED_PATCH.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        _EMBED_PATCH.stop()

    def tearDown(self) -> None:
        clear_active_gateway_orchestrator()
        super().tearDown()

    @patch('thalamus.thalamus.fire_spike')
    @patch('thalamus.signals.async_to_sync', _noop_async_to_sync)
    @patch('talos_gateway.signals.async_to_sync', _noop_async_to_sync)
    @patch('asgiref.sync.async_to_sync', _noop_async_to_sync)
    def test_inbound_ack_echoes_request_id(self, *_mocks):
        """Assert inbound_ack includes the request_id supplied on the request."""
        orch = GatewayOrchestrator()
        orch.load_adapters()
        set_active_gateway_orchestrator(orch)

        async def _run() -> None:
            body = json.dumps({
                'type': WS_MSG_INBOUND,
                'channel_id': 'chan-req-echo',
                'message_id': 'mid-req-echo',
                'content': 'echo test',
                'request_id': 'req-abc-1',
            })
            data = await _ws_connect_send_receive(body)
            self.assertEqual(data['type'], WS_MSG_INBOUND_ACK)
            self.assertEqual(data['request_id'], 'req-abc-1')

        asyncio.run(_run())

    @patch('thalamus.signals.async_to_sync', _noop_async_to_sync)
    @patch('talos_gateway.signals.async_to_sync', _noop_async_to_sync)
    @patch('asgiref.sync.async_to_sync', _noop_async_to_sync)
    def test_create_session_ack_echoes_request_id(self, *_mocks):
        """Assert create_session_ack echoes request_id."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_to(text_data=json.dumps({
                'type': WS_MSG_CREATE_SESSION,
                'channel_id': 'chan-echo-create',
                'request_id': 'req-create-2',
            }))
            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], WS_MSG_CREATE_SESSION_ACK)
            self.assertEqual(data['request_id'], 'req-create-2')
            await communicator.disconnect()

        asyncio.run(_run())

    @patch('thalamus.signals.async_to_sync', _noop_async_to_sync)
    @patch('talos_gateway.signals.async_to_sync', _noop_async_to_sync)
    @patch('asgiref.sync.async_to_sync', _noop_async_to_sync)
    def test_list_sessions_ack_echoes_request_id(self, *_mocks):
        """Assert list_sessions_ack echoes request_id."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_to(text_data=json.dumps({
                'type': WS_MSG_LIST_SESSIONS,
                'request_id': 'req-list-3',
            }))
            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], WS_MSG_LIST_SESSIONS_ACK)
            self.assertEqual(data['request_id'], 'req-list-3')
            await communicator.disconnect()

        asyncio.run(_run())


@override_settings(
    CHANNEL_LAYERS={
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
    }
)
class GatewayJoinInterruptRequestIdEchoTests(SimpleTestCase):
    """Assert join_session_ack / interrupt_ack echo request_id."""

    databases = '__all__'

    def test_join_session_ack_echoes_request_id(self):
        """Assert join_session_ack echoes the request_id when supplied."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            sid = str(uuid4())
            await communicator.send_to(text_data=json.dumps({
                'type': WS_MSG_JOIN_SESSION,
                'session_id': sid,
                'request_id': 'req-join-4',
            }))
            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], WS_MSG_JOIN_SESSION_ACK)
            self.assertEqual(data['request_id'], 'req-join-4')
            self.assertEqual(data['session_id'], sid)
            await communicator.disconnect()

        asyncio.run(_run())

    def test_interrupt_ack_echoes_request_id(self):
        """Assert interrupt_ack echoes request_id after joining a session."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            sid = str(uuid4())
            await communicator.send_to(text_data=json.dumps({
                'type': WS_MSG_JOIN_SESSION,
                'session_id': sid,
            }))
            await communicator.receive_from()

            with patch(
                'talos_gateway.stream_consumer.handle_interrupt',
                return_value={'success': True, 'spike_id': 'sp-1'},
            ):
                await communicator.send_to(text_data=json.dumps({
                    'type': WS_MSG_INTERRUPT,
                    'request_id': 'req-int-5',
                }))
                raw = await communicator.receive_from()
                data = json.loads(raw)
                self.assertEqual(data['type'], WS_MSG_INTERRUPT_ACK)
                self.assertEqual(data['request_id'], 'req-int-5')
                self.assertTrue(data['success'])

            await communicator.disconnect()

        asyncio.run(_run())
