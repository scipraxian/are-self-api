"""Tests for talos_gateway.message_router."""

import os
from unittest.mock import patch

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from common.tests.common_test_case import CommonFixturesAPITestCase
from talos_gateway.contracts import PlatformEnvelope
from talos_gateway.message_router import MessageRouter
from talos_gateway.runtime import wake_reasoning
from talos_gateway.session_manager import SessionManager

THALAMUS_DISC_PK = '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838'
FIRE_SPIKE_PATH = 'thalamus.thalamus.fire_spike'


@override_settings(
    TALOS_GATEWAY={
        'default_identity_disc': THALAMUS_DISC_PK,
        'session_timeout_minutes': 60,
    }
)
class MessageRouterTests(CommonFixturesAPITestCase):
    """Tests for MessageRouter dispatch path and payload construction.

    Tests the sync core of dispatch_inbound: resolve_session +
    wake_reasoning + queue verification. The async wrapper is thin
    glue — testing synchronously avoids event-loop conflicts with
    Django post_save signal handlers that call async_to_sync.
    """

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    @patch(FIRE_SPIKE_PATH)
    def test_dispatch_inbound_appends_swarm_queue(self, _mock_fire):
        """Assert inbound envelope content is queued on ReasoningSession."""
        ts = timezone.now()
        env = PlatformEnvelope(
            platform='cli',
            channel_id='chan-mr-1',
            sender_id='u1',
            sender_name='User',
            message_id='mid-1',
            content='queue me',
            timestamp=ts,
        )
        sm = SessionManager()
        gs, rs = sm.resolve_session('cli', 'chan-mr-1', env)
        wake_result = wake_reasoning(gs, rs, env.content)
        self.assertTrue(wake_result.get('success'))
        rs.refresh_from_db()
        self.assertEqual(len(rs.swarm_message_queue), 1)
        self.assertEqual(rs.swarm_message_queue[0]['content'], 'queue me')

    @patch(FIRE_SPIKE_PATH)
    def test_dispatch_inbound_returns_session_id(self, _mock_fire):
        """Assert wake_reasoning result includes session_id."""
        ts = timezone.now()
        env = PlatformEnvelope(
            platform='cli',
            channel_id='chan-mr-2',
            sender_id='u2',
            sender_name='User',
            message_id='mid-2',
            content='hello',
            timestamp=ts,
        )
        sm = SessionManager()
        gs, rs = sm.resolve_session('cli', 'chan-mr-2', env)
        result = wake_reasoning(gs, rs, env.content)
        self.assertEqual(result.get('session_id'), str(rs.pk))


class MessageRouterPayloadTests(SimpleTestCase):
    """Tests for MessageRouter.build_delivery_payload (no DB needed)."""

    def test_build_delivery_payload(self):
        """Assert DeliveryPayload construction matches outbound contract."""
        router = MessageRouter()
        p = router.build_delivery_payload(
            'discord',
            'c1',
            'reply text',
            thread_id='t1',
            is_voice=True,
            voice_audio_path='/tmp/a.mp3',
            reply_to='r1',
        )
        self.assertEqual(p.platform, 'discord')
        self.assertEqual(p.channel_id, 'c1')
        self.assertTrue(p.is_voice)
        self.assertEqual(p.voice_audio_path, '/tmp/a.mp3')
        self.assertEqual(p.reply_to, 'r1')
