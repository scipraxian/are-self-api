"""Tests for talos_gateway.stream_consumer."""

import asyncio
import json

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, override_settings
from django.urls import path

from talos_gateway.stream_consumer import GatewayTokenStreamConsumer


def _gateway_application():
    return URLRouter(
        [
            path(
                'ws/gateway/stream/',
                GatewayTokenStreamConsumer.as_asgi(),
            ),
        ]
    )


class GatewayTokenStreamConsumerTests(SimpleTestCase):
    """WebSocket tests using in-memory channel layer."""

    @override_settings(
        CHANNEL_LAYERS={
            'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
        }
    )
    def test_echo_json_message(self):
        """Assert client JSON is echoed in a structured envelope."""

        async def _run() -> None:
            communicator = WebsocketCommunicator(
                _gateway_application(),
                '/ws/gateway/stream/',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_to(text_data='{"token":"delta"}')
            raw = await communicator.receive_from()
            data = json.loads(raw)
            self.assertEqual(data['type'], 'echo')
            self.assertEqual(data['payload']['token'], 'delta')
            await communicator.disconnect()

        asyncio.run(_run())
