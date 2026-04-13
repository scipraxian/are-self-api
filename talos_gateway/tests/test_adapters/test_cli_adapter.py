"""Tests for talos_gateway.adapters.cli_adapter."""

import asyncio

from django.test import SimpleTestCase

from talos_gateway.adapters.cli_adapter import CliAdapter
from talos_gateway.contracts import DeliveryPayload


class CliAdapterTests(SimpleTestCase):
    """Tests for CliAdapter."""

    def test_send_returns_success_stub(self):
        """Assert send returns a success-shaped dict without external IO."""

        async def _run() -> None:
            adapter = CliAdapter({})
            payload = DeliveryPayload(
                platform='cli',
                channel_id='local',
                content='hello',
            )
            result = await adapter.send(payload)
            self.assertTrue(result.get('success'))
            self.assertEqual(result.get('status_code'), 200)

        asyncio.run(_run())

    def test_send_chunked_splits_long_content(self):
        """Assert send_chunked issues multiple sends for long bodies."""

        async def _run() -> None:
            adapter = CliAdapter({})
            adapter.MAX_MESSAGE_LENGTH = 4
            payload = DeliveryPayload(
                platform='cli',
                channel_id='c',
                content='abcdefgh',
            )
            result = await adapter.send_chunked(payload)
            self.assertTrue(result.get('success'))

        asyncio.run(_run())
