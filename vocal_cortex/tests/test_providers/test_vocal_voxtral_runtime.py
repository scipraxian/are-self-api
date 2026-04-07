"""Tests for vocal_cortex.providers.voxtral_runtime."""

from unittest.mock import patch

from django.test import SimpleTestCase

from vocal_cortex.providers import voxtral_runtime


class VocalVoxtralRuntimeTests(SimpleTestCase):
    """Tests for TTS model resolution and synthesis orchestration."""

    @patch('vocal_cortex.providers.voxtral_runtime.resolve_binary')
    def test_synthesize_fails_without_binary(self, mock_bin):
        """Assert missing binary returns typed failure."""
        mock_bin.return_value = None
        result = voxtral_runtime.synthesize_with_voxtral(
            'hello',
            '/tmp/out.wav',
            'voxtral',
            {},
        )
        self.assertFalse(result.success)
        self.assertIn('binary', result.error or '')
