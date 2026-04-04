"""Tests for talos_gateway.adapters.discord_adapter."""

import asyncio

from django.test import SimpleTestCase

from talos_gateway.adapters.discord_adapter import DiscordAdapter
from talos_gateway.contracts import DeliveryPayload


class DiscordAdapterTests(SimpleTestCase):
    """Tests for DiscordAdapter (SDK mocked by stub implementation)."""

    def test_platform_name_and_max_length(self):
        """Assert convention constants match Layer 4 defaults."""
        adapter = DiscordAdapter({})
        self.assertEqual(adapter.PLATFORM_NAME, 'discord')
        self.assertEqual(adapter.MAX_MESSAGE_LENGTH, 2000)

    def test_send_stub(self):
        """Assert send returns success without discord.py."""

        async def _run() -> None:
            adapter = DiscordAdapter({})
            result = await adapter.send(
                DeliveryPayload(
                    platform='discord',
                    channel_id='1',
                    content='ping',
                )
            )
            self.assertTrue(result.get('success'))

        asyncio.run(_run())
