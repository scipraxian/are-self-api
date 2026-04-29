from unittest.mock import MagicMock, patch

from django.test import TestCase

from frontal_lobe.synapse_client import (
    PROVIDER_OLLAMA,
    SynapseClient,
    UNLOAD_CONTENT,
    UNLOAD_KEEP_ALIVE,
    UNLOAD_MAX_TOKENS,
    UNLOAD_ROLE,
)


def _make_ledger(provider_key: str, base_url: str = 'http://ollama:11434'):
    """Build a MagicMock that walks like an AIModelProviderUsageRecord.

    SynapseClient only ever reads ledger.ai_model_provider.provider /
    .provider_unique_model_id, so a mock chain is enough — no DB needed.
    """
    ledger = MagicMock()
    ledger.ai_model_provider.provider_unique_model_id = (
        f'{provider_key}/test-model'
    )
    ledger.ai_model_provider.provider.key = provider_key
    ledger.ai_model_provider.provider.base_url = base_url
    ledger.ai_model_provider.provider.api_key_env_var = None
    return ledger


class SynapseClientUnloadTest(TestCase):
    """The KWARG_NUM_KEEP_ALIVE → KWARG_KEEP_ALIVE rename matters.

    LiteLLM's Ollama integration only forwards a directive named
    ``keep_alive``. The pre-rename ``num_keep_alive`` kwarg was silently
    dropped (``litellm.drop_params = True`` is set globally), so the model
    sat resident in VRAM after every call. Lock in the correct kwarg name.
    """

    @patch('frontal_lobe.synapse_client.litellm.completion')
    def test_unload_passes_keep_alive_kwarg_for_ollama(self, mock_completion):
        ledger = _make_ledger(PROVIDER_OLLAMA)
        client = SynapseClient(ledger)

        client.unload()

        mock_completion.assert_called_once()
        _, kwargs = mock_completion.call_args
        self.assertEqual(kwargs['keep_alive'], UNLOAD_KEEP_ALIVE)
        self.assertNotIn('num_keep_alive', kwargs)
        self.assertEqual(kwargs['model'], 'ollama/test-model')
        self.assertEqual(kwargs['max_tokens'], UNLOAD_MAX_TOKENS)
        self.assertEqual(
            kwargs['messages'],
            [{'role': UNLOAD_ROLE, 'content': UNLOAD_CONTENT}],
        )

    @patch('frontal_lobe.synapse_client.litellm.completion')
    def test_unload_no_op_for_non_ollama_provider(self, mock_completion):
        ledger = _make_ledger('openrouter')
        client = SynapseClient(ledger)

        client.unload()

        mock_completion.assert_not_called()
