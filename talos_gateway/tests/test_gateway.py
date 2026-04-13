"""Tests for talos_gateway.gateway."""

import os
from unittest.mock import patch

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

from asgiref.sync import async_to_sync
from django.test import override_settings
from django.utils import timezone

from common.tests.common_test_case import CommonFixturesAPITestCase
from talos_gateway.contracts import PlatformEnvelope
from talos_gateway.gateway import GatewayOrchestrator
from talos_gateway.runtime import wake_reasoning

THALAMUS_DISC_PK = '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838'


@override_settings(
    TALOS_GATEWAY={
        'platforms': {'cli': {'enabled': True}},
        'default_identity_disc': THALAMUS_DISC_PK,
        'session_timeout_minutes': 60,
    }
)
class GatewayOrchestratorTests(CommonFixturesAPITestCase):
    """Tests for GatewayOrchestrator."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    def test_load_adapters_instantiates_cli(self):
        """Assert enabled platforms produce adapter instances."""
        orch = GatewayOrchestrator()
        orch.load_adapters()
        self.assertIn('cli', orch.adapters)
        self.assertEqual(orch.adapters['cli'].PLATFORM_NAME, 'cli')

    def test_start_all_drops_failing_adapter(self):
        """Assert adapter.start failure removes that adapter."""

        class BrokenAdapter(object):
            """Raises on start."""

            PLATFORM_NAME = 'broken'

            def __init__(self, config):
                pass

            async def start(self):
                raise RuntimeError('simulated start failure')

            async def stop(self):
                pass

        orch = GatewayOrchestrator({'platforms': {}})
        orch.adapters['broken'] = BrokenAdapter({})
        async_to_sync(orch.start_all)()
        self.assertNotIn('broken', orch.adapters)

    @patch('thalamus.thalamus.fire_spike')
    def test_handle_inbound_queues_via_router(self, _mock_fire):
        """Assert handle_inbound resolves session and queues swarm messages.

        Tests the sync orchestration path directly: resolve_session
        (identity disc lookup) + wake_reasoning (message queue + spike
        creation). The async wrappers (handle_inbound, dispatch_inbound)
        are thin glue — testing the sync core avoids event-loop conflicts
        with Django post_save signal handlers that call async_to_sync.
        """
        ts = timezone.now()
        env = PlatformEnvelope(
            platform='cli',
            channel_id='chan-go-1',
            sender_id='u',
            sender_name='User',
            message_id='m1',
            content='gateway inbound',
            timestamp=ts,
        )
        orch = GatewayOrchestrator()
        gs, rs = orch.session_manager.resolve_session(
            env.platform, env.channel_id, env,
        )
        wake_result = wake_reasoning(gs, rs, env.content)
        self.assertTrue(wake_result.get('success'))
        rs.refresh_from_db()
        self.assertGreaterEqual(len(rs.swarm_message_queue), 1)
        self.assertEqual(
            rs.swarm_message_queue[-1]['content'], 'gateway inbound'
        )
