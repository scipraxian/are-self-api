"""Tests for talos_gateway.cli.client — single-dispatcher WebSocket client.

The CLI client owns exactly one WebSocket reader coroutine. Request methods
(``send_message``, ``send_interrupt``, etc.) correlate their replies via a
``request_id`` field echoed by the server on the matching ``*_ack`` frame;
they never call ``ws.recv()`` themselves. Unsolicited frames
(``token_delta``, ``response_complete``, ``session_status``, ``error``)
route to display callbacks.
"""

import asyncio
import json
from typing import Any, Optional
from unittest.mock import patch

from django.test import SimpleTestCase
from websockets.exceptions import ConnectionClosed

from talos_gateway.cli.client import CliClient, DisplayCallbacks
from talos_gateway.ws_protocol import (
    WS_MSG_CREATE_SESSION,
    WS_MSG_CREATE_SESSION_ACK,
    WS_MSG_ERROR,
    WS_MSG_INBOUND,
    WS_MSG_INBOUND_ACK,
    WS_MSG_INTERRUPT,
    WS_MSG_INTERRUPT_ACK,
    WS_MSG_JOIN_SESSION,
    WS_MSG_JOIN_SESSION_ACK,
    WS_MSG_LIST_SESSIONS,
    WS_MSG_LIST_SESSIONS_ACK,
    WS_MSG_RESPONSE_COMPLETE,
    WS_MSG_SESSION_STATUS,
    WS_MSG_TOKEN_DELTA,
)


class _FakeWebSocket(object):
    """Deterministic in-memory stand-in for a websockets client connection.

    Tracks how many coroutines are currently awaiting ``recv()`` and raises
    ``RuntimeError`` if it ever exceeds one — the same semantic the real
    ``websockets`` library enforces.
    """

    def __init__(self) -> None:
        self._incoming: asyncio.Queue = asyncio.Queue()
        self.sent_frames: list[str] = []
        self._recv_in_flight = 0
        self._closed = False

    async def send(self, raw: str) -> None:
        self.sent_frames.append(raw)

    async def recv(self) -> str:
        if self._recv_in_flight > 0:
            raise RuntimeError(
                'cannot call recv while another coroutine is already '
                'running recv or recv_streaming'
            )
        self._recv_in_flight += 1
        try:
            item = await self._incoming.get()
        finally:
            self._recv_in_flight -= 1
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        self._closed = True
        await self._incoming.put(
            ConnectionClosed(None, None)  # type: ignore[arg-type]
        )

    def push(self, frame: dict) -> None:
        """Queue a server-to-client JSON frame."""
        self._incoming.put_nowait(json.dumps(frame))

    def push_close(self) -> None:
        """Queue a synthetic connection-closed signal."""
        self._incoming.put_nowait(
            ConnectionClosed(None, None)  # type: ignore[arg-type]
        )

    @property
    def last_sent_json(self) -> dict:
        return json.loads(self.sent_frames[-1])


def _null_callbacks() -> DisplayCallbacks:
    """Build DisplayCallbacks that record nothing and never fail."""
    return DisplayCallbacks(
        on_token=lambda _t: None,
        on_complete=lambda _c, _s: None,
        on_status=lambda _s: None,
        on_error=lambda _c, _m: None,
    )


async def _start_client_with_fake_ws(
    callbacks: Optional[DisplayCallbacks] = None,
) -> tuple[CliClient, _FakeWebSocket]:
    """Instantiate CliClient and bind a ``_FakeWebSocket`` in-place of connect."""
    client = CliClient('ws://unused/test', 'cli-test')
    ws = _FakeWebSocket()

    async def _fake_connect(_url: str) -> _FakeWebSocket:
        return ws

    with patch('talos_gateway.cli.client.websockets.connect', _fake_connect):
        await client.start(callbacks or _null_callbacks())
    return client, ws


class CliClientConcurrentRecvTests(SimpleTestCase):
    """Round 1 — the primary bug: no concurrent ``recv()`` on the same socket."""

    def test_concurrent_requests_do_not_trigger_concurrent_recv(self):
        """Assert parallel send_message calls never raise the websockets recv race."""

        async def _run() -> None:
            client, ws = await _start_client_with_fake_ws()
            try:
                task_a = asyncio.create_task(client.send_message('a'))
                task_b = asyncio.create_task(client.send_message('b'))

                await asyncio.sleep(0)
                await asyncio.sleep(0)

                sent = [json.loads(raw) for raw in ws.sent_frames]
                req_a = next(
                    s for s in sent if s.get('content') == 'a'
                )['request_id']
                req_b = next(
                    s for s in sent if s.get('content') == 'b'
                )['request_id']

                ws.push({
                    'type': WS_MSG_INBOUND_ACK,
                    'request_id': req_b,
                    'result': {'success': True, 'label': 'b'},
                })
                ws.push({
                    'type': WS_MSG_INBOUND_ACK,
                    'request_id': req_a,
                    'result': {'success': True, 'label': 'a'},
                })

                ack_a = await asyncio.wait_for(task_a, timeout=1.0)
                ack_b = await asyncio.wait_for(task_b, timeout=1.0)
            finally:
                await client.stop()

            self.assertEqual(ack_a['result']['label'], 'a')
            self.assertEqual(ack_b['result']['label'], 'b')

        asyncio.run(_run())


class CliClientRequestIdCorrelationTests(SimpleTestCase):
    """Round 2 — acks resolve by ``request_id``, tolerant of interleaving."""

    def test_send_message_resolves_on_matching_ack(self):
        """Assert send_message returns the ack whose request_id matches the send."""

        async def _run() -> None:
            client, ws = await _start_client_with_fake_ws()
            try:
                task = asyncio.create_task(client.send_message('hi'))
                await asyncio.sleep(0)
                sent = ws.last_sent_json
                self.assertEqual(sent['type'], WS_MSG_INBOUND)
                self.assertEqual(sent['channel_id'], 'cli-test')
                self.assertEqual(sent['content'], 'hi')
                self.assertIn('request_id', sent)
                self.assertIn('message_id', sent)

                ws.push({
                    'type': WS_MSG_INBOUND_ACK,
                    'request_id': sent['request_id'],
                    'result': {'success': True},
                })
                ack = await asyncio.wait_for(task, timeout=1.0)
            finally:
                await client.stop()

            self.assertEqual(ack['type'], WS_MSG_INBOUND_ACK)
            self.assertTrue(ack['result']['success'])

        asyncio.run(_run())

    def test_token_deltas_before_ack_do_not_block_request(self):
        """Assert token_delta frames interleaved with an ack route correctly."""
        tokens: list[str] = []

        async def _run() -> None:
            cbs = DisplayCallbacks(
                on_token=lambda t: tokens.append(t),
                on_complete=lambda _c, _s: None,
                on_status=lambda _s: None,
                on_error=lambda _c, _m: None,
            )
            client, ws = await _start_client_with_fake_ws(cbs)
            try:
                task = asyncio.create_task(client.send_message('hi'))
                await asyncio.sleep(0)
                request_id = ws.last_sent_json['request_id']

                ws.push({'type': WS_MSG_TOKEN_DELTA, 'token': 'He'})
                ws.push({'type': WS_MSG_TOKEN_DELTA, 'token': 'llo'})
                ws.push({
                    'type': WS_MSG_INBOUND_ACK,
                    'request_id': request_id,
                    'result': {'success': True},
                })
                await asyncio.wait_for(task, timeout=1.0)
                await asyncio.sleep(0)
            finally:
                await client.stop()

            self.assertEqual(tokens, ['He', 'llo'])

        asyncio.run(_run())

    def test_concurrent_requests_resolve_by_request_id(self):
        """Assert two overlapping send_message calls each get their own ack."""

        async def _run() -> None:
            client, ws = await _start_client_with_fake_ws()
            try:
                task_a = asyncio.create_task(client.send_message('first'))
                task_b = asyncio.create_task(client.send_message('second'))
                await asyncio.sleep(0)

                sent = [json.loads(raw) for raw in ws.sent_frames]
                req_first = next(
                    s for s in sent if s['content'] == 'first'
                )['request_id']
                req_second = next(
                    s for s in sent if s['content'] == 'second'
                )['request_id']
                self.assertNotEqual(req_first, req_second)

                ws.push({
                    'type': WS_MSG_INBOUND_ACK,
                    'request_id': req_first,
                    'result': {'label': 'first'},
                })
                ws.push({
                    'type': WS_MSG_INBOUND_ACK,
                    'request_id': req_second,
                    'result': {'label': 'second'},
                })

                ack_a, ack_b = await asyncio.wait_for(
                    asyncio.gather(task_a, task_b), timeout=1.0
                )
            finally:
                await client.stop()

            self.assertEqual(ack_a['result']['label'], 'first')
            self.assertEqual(ack_b['result']['label'], 'second')

        asyncio.run(_run())

    def test_ack_for_unknown_request_id_is_dropped(self):
        """Assert unknown-request_id acks are ignored and the reader stays alive."""

        async def _run() -> None:
            client, ws = await _start_client_with_fake_ws()
            try:
                ws.push({
                    'type': WS_MSG_INBOUND_ACK,
                    'request_id': 'stray-request',
                    'result': {},
                })
                await asyncio.sleep(0)
                await asyncio.sleep(0)

                task = asyncio.create_task(client.send_message('ok'))
                await asyncio.sleep(0)
                request_id = ws.last_sent_json['request_id']
                ws.push({
                    'type': WS_MSG_INBOUND_ACK,
                    'request_id': request_id,
                    'result': {'success': True},
                })
                ack = await asyncio.wait_for(task, timeout=1.0)
            finally:
                await client.stop()

            self.assertTrue(ack['result']['success'])

        asyncio.run(_run())


class CliClientDisplayDispatchTests(SimpleTestCase):
    """Round 3 — display frames route to the right callback."""

    def test_token_delta_routes_to_on_token(self):
        """Assert token_delta frames invoke on_token in order."""
        tokens: list[str] = []

        async def _run() -> None:
            cbs = DisplayCallbacks(
                on_token=lambda t: tokens.append(t),
                on_complete=lambda _c, _s: None,
                on_status=lambda _s: None,
                on_error=lambda _c, _m: None,
            )
            client, ws = await _start_client_with_fake_ws(cbs)
            try:
                ws.push({'type': WS_MSG_TOKEN_DELTA, 'token': 'A'})
                ws.push({'type': WS_MSG_TOKEN_DELTA, 'token': 'B'})
                ws.push({'type': WS_MSG_TOKEN_DELTA, 'token': 'C'})
                for _ in range(4):
                    await asyncio.sleep(0)
            finally:
                await client.stop()

            self.assertEqual(tokens, ['A', 'B', 'C'])

        asyncio.run(_run())

    def test_response_complete_routes_to_on_complete(self):
        """Assert response_complete invokes on_complete with content and status."""
        completions: list[tuple[str, str]] = []

        async def _run() -> None:
            cbs = DisplayCallbacks(
                on_token=lambda _t: None,
                on_complete=lambda c, s: completions.append((c, s)),
                on_status=lambda _s: None,
                on_error=lambda _c, _m: None,
            )
            client, ws = await _start_client_with_fake_ws(cbs)
            try:
                ws.push({
                    'type': WS_MSG_RESPONSE_COMPLETE,
                    'content': 'Done.',
                    'session_status': '7',
                })
                for _ in range(3):
                    await asyncio.sleep(0)
            finally:
                await client.stop()

            self.assertEqual(completions, [('Done.', '7')])

        asyncio.run(_run())

    def test_session_status_routes_to_on_status(self):
        """Assert session_status invokes on_status callback."""
        statuses: list[str] = []

        async def _run() -> None:
            cbs = DisplayCallbacks(
                on_token=lambda _t: None,
                on_complete=lambda _c, _s: None,
                on_status=lambda s: statuses.append(s),
                on_error=lambda _c, _m: None,
            )
            client, ws = await _start_client_with_fake_ws(cbs)
            try:
                ws.push({
                    'type': WS_MSG_SESSION_STATUS,
                    'status': 'ACTIVE',
                })
                for _ in range(3):
                    await asyncio.sleep(0)
            finally:
                await client.stop()

            self.assertEqual(statuses, ['ACTIVE'])

        asyncio.run(_run())

    def test_error_without_request_id_routes_to_on_error(self):
        """Assert unsolicited error frames invoke on_error."""
        errors: list[tuple[str, str]] = []

        async def _run() -> None:
            cbs = DisplayCallbacks(
                on_token=lambda _t: None,
                on_complete=lambda _c, _s: None,
                on_status=lambda _s: None,
                on_error=lambda code, msg: errors.append((code, msg)),
            )
            client, ws = await _start_client_with_fake_ws(cbs)
            try:
                ws.push({
                    'type': WS_MSG_ERROR,
                    'code': 'gateway_unavailable',
                    'message': 'not running',
                })
                for _ in range(3):
                    await asyncio.sleep(0)
            finally:
                await client.stop()

            self.assertEqual(errors, [('gateway_unavailable', 'not running')])

        asyncio.run(_run())


class CliClientShutdownTests(SimpleTestCase):
    """Round 4 — stop() cancels reader and fails pending futures cleanly."""

    def test_stop_cancels_reader_and_closes_socket(self):
        """Assert stop() closes the socket and cancels the reader task."""

        async def _run() -> tuple[bool, bool]:
            client, ws = await _start_client_with_fake_ws()
            reader_task = client._reader_task
            self.assertIsNotNone(reader_task)
            await client.stop()
            return ws._closed, reader_task.done()

        closed, done = asyncio.run(_run())
        self.assertTrue(closed)
        self.assertTrue(done)

    def test_stop_fails_pending_requests_with_connection_closed(self):
        """Assert pending send_message awaits raise ConnectionClosed on stop."""

        async def _run() -> Any:
            client, _ws = await _start_client_with_fake_ws()
            task = asyncio.create_task(client.send_message('stuck'))
            await asyncio.sleep(0)
            await client.stop()
            with self.assertRaises(ConnectionClosed):
                await asyncio.wait_for(task, timeout=1.0)

        asyncio.run(_run())


class CliClientPayloadShapeTests(SimpleTestCase):
    """Verify every request method emits the correct frame shape."""

    def test_send_interrupt_payload_includes_request_id(self):
        """Assert interrupt frame has the correct type and a request_id."""

        async def _run() -> None:
            client, ws = await _start_client_with_fake_ws()
            try:
                task = asyncio.create_task(client.send_interrupt())
                await asyncio.sleep(0)
                sent = ws.last_sent_json
                self.assertEqual(sent['type'], WS_MSG_INTERRUPT)
                self.assertIn('request_id', sent)

                ws.push({
                    'type': WS_MSG_INTERRUPT_ACK,
                    'request_id': sent['request_id'],
                    'success': True,
                })
                await asyncio.wait_for(task, timeout=1.0)
            finally:
                await client.stop()

        asyncio.run(_run())

    def test_send_join_session_payload(self):
        """Assert join_session frame carries session_id and request_id."""

        async def _run() -> None:
            client, ws = await _start_client_with_fake_ws()
            try:
                task = asyncio.create_task(client.send_join_session('sid-7'))
                await asyncio.sleep(0)
                sent = ws.last_sent_json
                self.assertEqual(sent['type'], WS_MSG_JOIN_SESSION)
                self.assertEqual(sent['session_id'], 'sid-7')
                self.assertIn('request_id', sent)

                ws.push({
                    'type': WS_MSG_JOIN_SESSION_ACK,
                    'request_id': sent['request_id'],
                    'session_id': 'sid-7',
                })
                ack = await asyncio.wait_for(task, timeout=1.0)
            finally:
                await client.stop()

            self.assertEqual(ack['session_id'], 'sid-7')

        asyncio.run(_run())

    def test_send_list_sessions_returns_session_list(self):
        """Assert list_sessions resolves with the sessions list from the ack."""

        async def _run() -> list[dict]:
            client, ws = await _start_client_with_fake_ws()
            try:
                task = asyncio.create_task(client.send_list_sessions())
                await asyncio.sleep(0)
                sent = ws.last_sent_json
                self.assertEqual(sent['type'], WS_MSG_LIST_SESSIONS)
                self.assertIn('request_id', sent)

                ws.push({
                    'type': WS_MSG_LIST_SESSIONS_ACK,
                    'request_id': sent['request_id'],
                    'sessions': [{'session_id': 's1', 'channel_id': 'c1'}],
                })
                sessions = await asyncio.wait_for(task, timeout=1.0)
            finally:
                await client.stop()
            return sessions

        sessions = asyncio.run(_run())
        self.assertEqual(sessions, [{'session_id': 's1', 'channel_id': 'c1'}])

    def test_send_create_session_payload(self):
        """Assert create_session frame includes channel_id and request_id."""

        async def _run() -> None:
            client, ws = await _start_client_with_fake_ws()
            try:
                task = asyncio.create_task(client.send_create_session())
                await asyncio.sleep(0)
                sent = ws.last_sent_json
                self.assertEqual(sent['type'], WS_MSG_CREATE_SESSION)
                self.assertEqual(sent['channel_id'], 'cli-test')
                self.assertIn('request_id', sent)

                ws.push({
                    'type': WS_MSG_CREATE_SESSION_ACK,
                    'request_id': sent['request_id'],
                    'session_id': 'new-session',
                    'channel_id': 'cli-test',
                })
                ack = await asyncio.wait_for(task, timeout=1.0)
            finally:
                await client.stop()

            self.assertEqual(ack['session_id'], 'new-session')

        asyncio.run(_run())
