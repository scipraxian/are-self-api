"""Tests for talos_gateway.delivery."""

from django.test import SimpleTestCase

from talos_gateway.contracts import DeliveryPayload
from talos_gateway.delivery import DeliveryService, send_with_retries


class FakeClockAdapter(object):
    """Minimal async adapter for delivery tests."""

    PLATFORM_NAME = 'fake'
    MAX_MESSAGE_LENGTH = 10

    def __init__(self):
        self.calls = []
        self.responses = []

    async def send(self, payload: DeliveryPayload) -> dict:
        self.calls.append(payload)
        if self.responses:
            return self.responses.pop(0)
        return {'success': True, 'message_id': '1', 'status_code': 200}


class TestSendWithRetries(SimpleTestCase):
    """Tests for send_with_retries."""

    async def test_succeeds_first_try(self):
        """Assert no sleeps when send succeeds immediately."""
        sleeps: list[float] = []
        adapter = FakeClockAdapter()
        adapter.responses = [{'success': True, 'status_code': 200}]
        payload = DeliveryPayload(platform='fake', channel_id='c', content='hi')

        async def sleep_fn(seconds: float) -> None:
            sleeps.append(seconds)

        result = await send_with_retries(adapter, payload, sleep_fn)
        self.assertTrue(result['success'])
        self.assertEqual(sleeps, [])

    async def test_retries_then_success(self):
        """Assert backoff sleeps occur before later attempts."""
        sleeps: list[float] = []
        adapter = FakeClockAdapter()
        adapter.responses = [
            {'success': False, 'status_code': 500},
            {'success': True, 'status_code': 200},
        ]
        payload = DeliveryPayload(platform='fake', channel_id='c', content='x')

        async def sleep_fn(seconds: float) -> None:
            sleeps.append(seconds)

        result = await send_with_retries(adapter, payload, sleep_fn)
        self.assertTrue(result['success'])
        self.assertEqual(sleeps, [1.0])

    async def test_no_retry_on_403(self):
        """Assert permanent failure codes do not schedule further attempts."""
        sleeps: list[float] = []
        adapter = FakeClockAdapter()
        adapter.responses = [{'success': False, 'status_code': 403}]
        payload = DeliveryPayload(platform='fake', channel_id='c', content='x')

        async def sleep_fn(seconds: float) -> None:
            sleeps.append(seconds)

        result = await send_with_retries(adapter, payload, sleep_fn)
        self.assertFalse(result['success'])
        self.assertEqual(sleeps, [])

    async def test_429_waits_retry_after(self):
        """Assert 429 responses wait for retry_after_seconds."""
        sleeps: list[float] = []
        adapter = FakeClockAdapter()
        adapter.responses = [
            {'success': False, 'status_code': 429, 'retry_after_seconds': 2.5},
            {'success': True, 'status_code': 200},
        ]
        payload = DeliveryPayload(platform='fake', channel_id='c', content='x')

        async def sleep_fn(seconds: float) -> None:
            sleeps.append(seconds)

        result = await send_with_retries(adapter, payload, sleep_fn)
        self.assertTrue(result['success'])
        self.assertIn(2.5, sleeps)


class TestDeliveryService(SimpleTestCase):
    """Tests for DeliveryService."""

    async def test_unknown_platform(self):
        """Assert missing adapter returns structured error."""
        service = DeliveryService({})
        payload = DeliveryPayload(platform='nope', channel_id='c', content='a')
        result = await service.send(payload)
        self.assertFalse(result['success'])
        self.assertEqual(result.get('error'), 'unknown_platform')

    async def test_chunked_send_multiple_calls(self):
        """Assert oversized content triggers multiple adapter sends."""
        adapter = FakeClockAdapter()
        adapter.MAX_MESSAGE_LENGTH = 4
        service = DeliveryService({'fake': adapter})
        payload = DeliveryPayload(
            platform='fake',
            channel_id='c',
            content='abcdefgh',
        )
        result = await service.send(payload)
        self.assertTrue(result['success'])
        self.assertEqual(len(adapter.calls), 2)

    async def test_cli_platform_is_noop_and_returns_success(self):
        """Assert CLI platform short-circuits without calling any adapter.

        CLI delivery is streamed via the Channels group bound to the
        reasoning session; ``DeliveryService`` should never drive it
        through an adapter even if one is somehow registered.
        """
        adapter = FakeClockAdapter()
        service = DeliveryService({'cli': adapter})
        payload = DeliveryPayload(
            platform='cli',
            channel_id='chan-noop',
            content='streamed via channels',
        )
        result = await service.send(payload)
        self.assertTrue(result.get('success'))
        self.assertEqual(adapter.calls, [])

    async def test_cli_platform_short_circuits_without_registered_adapter(self):
        """Assert CLI platform returns success even when no adapter is registered."""
        service = DeliveryService({})
        payload = DeliveryPayload(
            platform='cli',
            channel_id='chan-noop-2',
            content='no adapter',
        )
        result = await service.send(payload)
        self.assertTrue(result.get('success'))
