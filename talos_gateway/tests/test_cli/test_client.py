"""Tests for talos_gateway.cli.client — WebSocket client for CLI transport."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from talos_gateway.cli.client import CliClient
from talos_gateway.ws_protocol import (
    WS_MSG_CREATE_SESSION,
    WS_MSG_ERROR,
    WS_MSG_INBOUND,
    WS_MSG_INTERRUPT,
    WS_MSG_JOIN_SESSION,
    WS_MSG_LIST_SESSIONS,
    WS_MSG_RESPONSE_COMPLETE,
    WS_MSG_TOKEN_DELTA,
)


def _mock_ws():
    """Build a mock WebSocket with send/recv/close."""
    ws = AsyncMock()
    ws.close = AsyncMock()
    return ws


class CliClientPayloadTests(SimpleTestCase):
    """Assert outbound message payloads are constructed correctly."""

    def test_send_message_constructs_correct_payload(self):
        """Assert inbound message JSON has correct type/channel_id/content/message_id."""
        client = CliClient('ws://localhost:8001/ws/gateway/stream/', 'cli-test')
        ws = _mock_ws()
        client._ws = ws

        async def _run():
            ws.recv = AsyncMock(
                return_value=json.dumps({'type': 'inbound_ack', 'result': {}})
            )
            await client.send_message('hello')
            sent_raw = ws.send.call_args[0][0]
            sent = json.loads(sent_raw)
            self.assertEqual(sent['type'], WS_MSG_INBOUND)
            self.assertEqual(sent['channel_id'], 'cli-test')
            self.assertEqual(sent['content'], 'hello')
            self.assertIn('message_id', sent)

        asyncio.run(_run())

    def test_send_interrupt_constructs_correct_payload(self):
        """Assert interrupt message has correct type."""
        client = CliClient('ws://localhost:8001/ws/gateway/stream/', 'cli-test')
        ws = _mock_ws()
        client._ws = ws

        async def _run():
            ws.recv = AsyncMock(
                return_value=json.dumps({'type': 'interrupt_ack', 'success': True})
            )
            await client.send_interrupt()
            sent = json.loads(ws.send.call_args[0][0])
            self.assertEqual(sent['type'], WS_MSG_INTERRUPT)

        asyncio.run(_run())

    def test_send_join_session_constructs_correct_payload(self):
        """Assert join_session message includes session_id."""
        client = CliClient('ws://localhost:8001/ws/gateway/stream/', 'cli-test')
        ws = _mock_ws()
        client._ws = ws

        async def _run():
            ws.recv = AsyncMock(
                return_value=json.dumps(
                    {'type': 'join_session_ack', 'session_id': 'sid-1'}
                )
            )
            await client.send_join_session('sid-1')
            sent = json.loads(ws.send.call_args[0][0])
            self.assertEqual(sent['type'], WS_MSG_JOIN_SESSION)
            self.assertEqual(sent['session_id'], 'sid-1')

        asyncio.run(_run())


class CliClientListenTests(SimpleTestCase):
    """Assert the listen loop dispatches events to callbacks."""

    def test_listen_dispatches_token_delta(self):
        """Assert on_token callback invoked for token_delta messages."""
        client = CliClient('ws://localhost:8001/ws/gateway/stream/', 'cli-test')
        ws = _mock_ws()
        client._ws = ws

        tokens = []

        async def _run():
            messages = [
                json.dumps({'type': WS_MSG_TOKEN_DELTA, 'token': 'Hello'}),
                json.dumps({'type': WS_MSG_TOKEN_DELTA, 'token': ' world'}),
            ]
            call_count = 0

            async def _recv():
                nonlocal call_count
                if call_count < len(messages):
                    msg = messages[call_count]
                    call_count += 1
                    return msg
                raise asyncio.CancelledError()

            ws.recv = _recv
            try:
                await client.listen(
                    on_token=lambda t: tokens.append(t),
                    on_complete=lambda c, s: None,
                    on_status=lambda s: None,
                    on_error=lambda c, m: None,
                )
            except asyncio.CancelledError:
                pass

        asyncio.run(_run())
        self.assertEqual(tokens, ['Hello', ' world'])

    def test_listen_dispatches_response_complete(self):
        """Assert on_complete callback invoked for response_complete messages."""
        client = CliClient('ws://localhost:8001/ws/gateway/stream/', 'cli-test')
        ws = _mock_ws()
        client._ws = ws

        completions = []

        async def _run():
            messages = [
                json.dumps({
                    'type': WS_MSG_RESPONSE_COMPLETE,
                    'content': 'Done.',
                    'session_status': '7',
                }),
            ]
            call_count = 0

            async def _recv():
                nonlocal call_count
                if call_count < len(messages):
                    msg = messages[call_count]
                    call_count += 1
                    return msg
                raise asyncio.CancelledError()

            ws.recv = _recv
            try:
                await client.listen(
                    on_token=lambda t: None,
                    on_complete=lambda c, s: completions.append((c, s)),
                    on_status=lambda s: None,
                    on_error=lambda c, m: None,
                )
            except asyncio.CancelledError:
                pass

        asyncio.run(_run())
        self.assertEqual(completions, [('Done.', '7')])

    def test_listen_dispatches_error(self):
        """Assert on_error callback invoked for error messages."""
        client = CliClient('ws://localhost:8001/ws/gateway/stream/', 'cli-test')
        ws = _mock_ws()
        client._ws = ws

        errors = []

        async def _run():
            messages = [
                json.dumps({
                    'type': WS_MSG_ERROR,
                    'code': 'gateway_unavailable',
                    'message': 'not running',
                }),
            ]
            call_count = 0

            async def _recv():
                nonlocal call_count
                if call_count < len(messages):
                    msg = messages[call_count]
                    call_count += 1
                    return msg
                raise asyncio.CancelledError()

            ws.recv = _recv
            try:
                await client.listen(
                    on_token=lambda t: None,
                    on_complete=lambda c, s: None,
                    on_status=lambda s: None,
                    on_error=lambda c, m: errors.append((c, m)),
                )
            except asyncio.CancelledError:
                pass

        asyncio.run(_run())
        self.assertEqual(errors, [('gateway_unavailable', 'not running')])
