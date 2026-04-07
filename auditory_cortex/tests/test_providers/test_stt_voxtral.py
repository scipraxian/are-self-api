"""Tests for stt_voxtral provider."""

from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from auditory_cortex.providers import stt_voxtral


class SttVoxtralTests(SimpleTestCase):
    """Tests for Voxtral STT provider."""

    @patch(
        'auditory_cortex.providers.stt_voxtral.voxtral_runtime.transcribe_with_voxtral',
    )
    def test_transcribe_delegates_to_runtime(self, mock_tx):
        """Assert provider calls voxtral_runtime.transcribe_with_voxtral."""
        from auditory_cortex.contracts import success_result

        mock_tx.return_value = success_result('voxtral', 'hello', language='en')
        result = async_to_sync(stt_voxtral.transcribe)(
            '/tmp/a.wav',
            provider_name='voxtral',
            provider_config={'timeout_seconds': 30},
        )
        self.assertTrue(result.success)
        self.assertEqual(result.text, 'hello')
        mock_tx.assert_called_once()
