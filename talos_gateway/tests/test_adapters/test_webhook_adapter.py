"""Tests for talos_gateway.adapters.webhook_adapter."""

import asyncio

from django.test import SimpleTestCase

from talos_gateway.adapters.webhook_adapter import WebhookAdapter
from talos_gateway.contracts import DeliveryPayload


class WebhookAdapterTests(SimpleTestCase):
    """Tests for WebhookAdapter."""

    def test_send_returns_stub(self):
        """Assert webhook adapter send is stubbed for CI."""

        async def _run() -> None:
            adapter = WebhookAdapter({})
            result = await adapter.send(
                DeliveryPayload(
                    platform='webhook',
                    channel_id='hook',
                    content='x',
                )
            )
            self.assertTrue(result.get('success'))

        asyncio.run(_run())
