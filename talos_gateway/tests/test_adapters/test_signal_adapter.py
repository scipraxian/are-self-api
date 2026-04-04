"""Tests for talos_gateway.adapters.signal_adapter."""

import asyncio

from django.test import SimpleTestCase

from talos_gateway.adapters.signal_adapter import SignalAdapter
from talos_gateway.contracts import DeliveryPayload


class SignalAdapterTests(SimpleTestCase):
    """Tests for SignalAdapter."""

    def test_on_message_registers_callback(self):
        """Assert on_message stores handler reference."""

        async def _cb(_envelope):
            pass

        adapter = SignalAdapter({})
        adapter.on_message(_cb)
        self.assertIs(adapter._on_message, _cb)

    def test_send_stub(self):
        """Assert send returns success without signal-cli."""

        async def _run() -> None:
            adapter = SignalAdapter({})
            result = await adapter.send(
                DeliveryPayload(
                    platform='signal',
                    channel_id='+1',
                    content='hi',
                )
            )
            self.assertTrue(result.get('success'))

        asyncio.run(_run())
