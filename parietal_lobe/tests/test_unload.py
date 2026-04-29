from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import async_to_sync
from django.test import TestCase
from requests.exceptions import RequestException

from parietal_lobe.parietal_lobe import (
    ParietalLobe,
    _sync_unload_execution,
)


def _make_ledger(
    provider_key: str = 'ollama',
    base_url: str = 'http://ollama:11434',
    model_id: str = 'ollama/qwen2.5-coder:7b',
):
    """Mock-walk an AIModelProviderUsageRecord.

    _sync_unload_execution only reads ledger.ai_model_provider.provider.key,
    .base_url, and .ai_model_provider.provider_unique_model_id.
    """
    ledger = MagicMock()
    ledger.ai_model_provider.provider.key = provider_key
    ledger.ai_model_provider.provider.base_url = base_url
    ledger.ai_model_provider.provider_unique_model_id = model_id
    return ledger


class SyncUnloadExecutionTest(TestCase):
    """Direct-HTTP unload bypasses LiteLLM.

    LiteLLM may strip ``keep_alive`` because it isn't a standard
    OpenAI-compatible param and ``litellm.drop_params = True`` is set
    globally. The unload path therefore POSTs directly to Ollama's
    /api/chat with the bare {model, keep_alive: 0} envelope.
    """

    @patch('parietal_lobe.parietal_lobe.requests.post')
    def test_ollama_post_strips_provider_prefix(self, mock_post):
        ledger = _make_ledger(model_id='ollama/qwen2.5-coder:7b')

        _sync_unload_execution(ledger)

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], 'http://ollama:11434/api/chat')
        self.assertEqual(
            kwargs['json'],
            {'model': 'qwen2.5-coder:7b', 'keep_alive': 0},
        )
        self.assertEqual(kwargs['timeout'], 2)

    @patch('parietal_lobe.parietal_lobe.requests.post')
    def test_model_id_without_prefix_passes_through(self, mock_post):
        ledger = _make_ledger(model_id='nomic-embed-text')

        _sync_unload_execution(ledger)

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['model'], 'nomic-embed-text')

    @patch('parietal_lobe.parietal_lobe.requests.post')
    def test_no_op_for_non_ollama_provider(self, mock_post):
        # Cloud providers have no local VRAM to drop.
        ledger = _make_ledger(
            provider_key='openrouter',
            base_url='https://openrouter.ai/api',
            model_id='openrouter/anthropic/claude-3.5-sonnet',
        )

        _sync_unload_execution(ledger)

        mock_post.assert_not_called()

    @patch('parietal_lobe.parietal_lobe.requests.post')
    def test_no_post_when_base_url_missing(self, mock_post):
        ledger = _make_ledger(base_url='')

        _sync_unload_execution(ledger)

        mock_post.assert_not_called()

    @patch('parietal_lobe.parietal_lobe.requests.post')
    def test_provider_key_match_is_case_insensitive(self, mock_post):
        ledger = _make_ledger(provider_key='Ollama')

        _sync_unload_execution(ledger)

        mock_post.assert_called_once()

    @patch('parietal_lobe.parietal_lobe.requests.post')
    def test_request_exception_is_swallowed(self, mock_post):
        # Unload is a fire-and-forget signal; a network blip must not
        # bubble up and tear down the spike train's finally-block.
        mock_post.side_effect = RequestException('connection refused')
        ledger = _make_ledger()

        # Must not raise.
        _sync_unload_execution(ledger)

        mock_post.assert_called_once()


class ParietalLobeLedgerWiringTest(TestCase):
    """ParietalLobe routes the recorded ledger to the unload path."""

    def setUp(self):
        # Mock session so the ParietalLobe constructor (which reads
        # session.identity_disc.enabled_tools) doesn't need DB rows.
        self.session = MagicMock()
        self.session.identity_disc = None
        self.parietal_lobe = ParietalLobe(self.session, lambda msg: None)

    def test_record_last_used_ledger_sets_state(self):
        ledger = _make_ledger()

        self.parietal_lobe.record_last_used_ledger(ledger)

        self.assertIs(self.parietal_lobe._last_used_ledger, ledger)

    @patch('parietal_lobe.parietal_lobe._sync_unload_execution')
    def test_unload_client_routes_recorded_ledger(self, mock_sync_unload):
        ledger = _make_ledger()
        self.parietal_lobe.record_last_used_ledger(ledger)

        async_to_sync(self.parietal_lobe.unload_client)()

        mock_sync_unload.assert_called_once_with(ledger)

    @patch('parietal_lobe.parietal_lobe._sync_unload_execution')
    def test_unload_client_no_op_when_no_ledger(self, mock_sync_unload):
        # No record_last_used_ledger call — covers the case where every
        # synapse.chat() failed (model rejection / hypothalamus paralysis).
        async_to_sync(self.parietal_lobe.unload_client)()

        mock_sync_unload.assert_not_called()
