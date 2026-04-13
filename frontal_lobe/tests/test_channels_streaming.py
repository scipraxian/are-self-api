"""Tests for Layer 2 §3.2 Channels token streaming."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from frontal_lobe.channels_streaming import (
    TokenChannelSender,
    reasoning_session_group_name,
)


class TestReasoningSessionGroupName(SimpleTestCase):
    def test_stable_prefix(self):
        sid = uuid4()
        self.assertEqual(
            reasoning_session_group_name(sid),
            'session_%s' % sid,
        )


class TestTokenChannelSender(SimpleTestCase):
    def test_group_send_payload(self):
        sid = uuid4()
        sender = TokenChannelSender(sid)
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()

        with patch(
            'frontal_lobe.channels_streaming.get_channel_layer',
            return_value=mock_layer,
        ):

            async def run():
                await sender('hello')

            async_to_sync(run)()

        mock_layer.group_send.assert_called_once()
        call_args = mock_layer.group_send.call_args[0]
        self.assertEqual(call_args[0], reasoning_session_group_name(sid))
        self.assertEqual(
            call_args[1],
            {'type': 'token_delta', 'token': 'hello'},
        )
