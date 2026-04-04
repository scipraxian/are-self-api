"""Tests for talos_gateway.gateway."""

from asgiref.sync import async_to_sync
from django.test import override_settings
from django.utils import timezone

from common.tests.common_test_case import CommonFixturesAPITestCase

from talos_gateway.contracts import PlatformEnvelope
from talos_gateway.gateway import GatewayOrchestrator

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
        """Assert adapter.start failure removes that adapter (Layer 4 §7.1)."""

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

    def test_handle_inbound_queues_via_router(self):
        """Assert handle_inbound resolves session and queues swarm messages."""
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
        result = async_to_sync(orch.handle_inbound)(env)
        self.assertTrue(result.get('success'))
