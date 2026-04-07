"""Tests for SynapseClient streaming and Anthropic cache headers."""

from unittest.mock import MagicMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from frontal_lobe.synapse_client import PROVIDER_OLLAMA, SynapseClient
from hypothalamus.models import AIModelProviderUsageRecord


def _ledger_mock(provider_key: str = 'ollama') -> AIModelProviderUsageRecord:
    ledger = MagicMock(spec=AIModelProviderUsageRecord)
    ledger.request_payload = [{'role': 'user', 'content': 'hi'}]
    ledger.tool_payload = {}
    ledger.ai_model_provider = MagicMock()
    ledger.ai_model_provider.provider_unique_model_id = 'test/model'
    ledger.ai_model_provider.rate_limit_counter = 0
    prov = MagicMock()
    prov.key = provider_key
    prov.base_url = 'http://localhost:11434'
    prov.requires_api_key = False
    prov.api_key_env_var = None
    ledger.ai_model_provider.provider = prov
    return ledger


class MockAsyncStream(object):
    """Minimal async iterator for streaming chunks."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.idx >= len(self.chunks):
            raise StopAsyncIteration
        c = self.chunks[self.idx]
        self.idx += 1
        return c


class TestBuildKwargsAnthropic(SimpleTestCase):
    """Assert Anthropic beta header is present only for Anthropic provider."""

    def test_anthropic_gets_prompt_caching_header(self):
        ledger = _ledger_mock(provider_key='anthropic')
        client = SynapseClient(ledger)
        kwargs = client._build_kwargs(
            [{'role': 'user', 'content': 'x'}],
            None,
            {},
            stream=False,
        )
        self.assertIn('extra_headers', kwargs)
        self.assertIn(
            'prompt-caching-2024-07-31',
            kwargs['extra_headers'].get('anthropic-beta', ''),
        )

    def test_ollama_no_cache_header(self):
        ledger = _ledger_mock(provider_key=PROVIDER_OLLAMA)
        client = SynapseClient(ledger)
        kwargs = client._build_kwargs(
            [{'role': 'user', 'content': 'x'}],
            None,
            {},
            stream=False,
        )
        self.assertNotIn('extra_headers', kwargs)


class TestChatStream(SimpleTestCase):
    """Assert streaming invokes callback and stamps ledger."""

    def test_stream_callback_per_token(self):
        chunks = []
        for ch in ('Hel', 'lo'):
            m = MagicMock()
            m.choices = [MagicMock()]
            m.choices[0].delta = MagicMock(content=ch)
            chunks.append(m)

        final = MagicMock()
        final.choices = [MagicMock()]
        final.choices[0].message = MagicMock(content='Hello', tool_calls=None)
        final.usage = None
        final.model_dump = lambda: {'choices': [{'message': {'content': 'Hello'}}]}

        tokens = []

        async def on_delta(t: str) -> None:
            tokens.append(t)

        async def fake_acompletion(*args, **kwargs):
            return MockAsyncStream(chunks)

        ledger = _ledger_mock()

        with patch('frontal_lobe.synapse_client.litellm.acompletion', fake_acompletion):
            with patch(
                'frontal_lobe.synapse_client.litellm.stream_chunk_builder',
                return_value=final,
            ):
                client = SynapseClient(ledger)

                async def run():
                    return await client.chat_stream(
                        stream_callback=on_delta,
                        interrupt_check=None,
                    )

                ok, tool_calls = async_to_sync(run)()
        self.assertTrue(ok)
        self.assertEqual(''.join(tokens), 'Hello')
        self.assertEqual(tool_calls, [])

    def test_interrupt_raises_between_chunks(self):
        chunks = []
        for _ in range(2):
            m = MagicMock()
            m.choices = [MagicMock()]
            m.choices[0].delta = MagicMock(content='x')
            chunks.append(m)

        async def fake_acompletion(*args, **kwargs):
            return MockAsyncStream(chunks)

        ledger = _ledger_mock()
        calls = [0]

        def interrupt_check():
            calls[0] += 1
            return calls[0] >= 2

        with patch('frontal_lobe.synapse_client.litellm.acompletion', fake_acompletion):
            client = SynapseClient(ledger)

            async def run():
                await client.chat_stream(
                    stream_callback=None,
                    interrupt_check=interrupt_check,
                )

            with self.assertRaises(InterruptedError):
                async_to_sync(run)()
