"""Tests for tts_voxtral provider."""

from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from vocal_auditory_cortex.contracts import tts_success_result
from vocal_auditory_cortex.providers import tts_voxtral


class TtsVoxtralTests(SimpleTestCase):
    """Tests for Voxtral TTS provider."""

    @patch('vocal_auditory_cortex.providers.tts_voxtral.host_paths.provider_writable_temp')
    @patch(
        'vocal_auditory_cortex.providers.tts_voxtral.voxtral_runtime.synthesize_with_voxtral'
    )
    def test_synthesize_delegates_to_runtime(self, mock_syn, mock_tmp):
        """Assert provider calls voxtral_runtime.synthesize_with_voxtral."""
        mock_tmp.return_value = '/tmp/out.wav'
        mock_syn.return_value = tts_success_result(
            'voxtral', '/tmp/out.wav', format='wav'
        )
        result = async_to_sync(tts_voxtral.synthesize)(
            'hello',
            provider_name='voxtral',
            provider_config={},
        )
        self.assertTrue(result.success)
        mock_syn.assert_called_once()
