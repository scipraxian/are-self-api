"""Tests for vocal_auditory_cortex.providers.voxtral_runtime (STT and TTS)."""

from unittest.mock import patch

from django.test import SimpleTestCase

from vocal_auditory_cortex.providers import voxtral_runtime


class VoxtralRuntimeAsrTests(SimpleTestCase):
    """Tests for binary resolution and ASR orchestration."""

    @patch('vocal_auditory_cortex.providers.voxtral_runtime.resolve_binary')
    def test_transcribe_with_voxtral_fails_without_binary(self, mock_bin):
        """Assert missing binary returns typed failure."""
        mock_bin.return_value = None
        result = voxtral_runtime.transcribe_with_voxtral(
            '/tmp/a.wav',
            'voxtral',
            {},
        )
        self.assertFalse(result.success)
        self.assertIn('binary', result.error or '')


class VoxtralRuntimeTtsTests(SimpleTestCase):
    """Tests for TTS orchestration."""

    @patch('vocal_auditory_cortex.providers.voxtral_runtime.resolve_binary')
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
