"""Tests for tts_elevenlabs provider."""

import os
from unittest.mock import MagicMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from vocal_cortex.providers import tts_elevenlabs


class TtsElevenlabsTests(SimpleTestCase):
    """Tests for ElevenLabs TTS provider."""

    def test_returns_failure_without_api_key(self):
        """Assert missing API key is rejected."""
        with patch.dict(os.environ, {'ELEVENLABS_API_KEY': ''}):
            result = async_to_sync(tts_elevenlabs.synthesize)(
                'hello',
                provider_name='elevenlabs',
                provider_config={'voice_id': 'vid123'},
            )
        self.assertFalse(result.success)
        self.assertIn('API key', result.error or '')

    @patch('vocal_cortex.providers.tts_elevenlabs.requests.post')
    def test_success_writes_temp_mp3(self, mock_post):
        """Assert HTTP 200 writes response bytes to a temp file."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ''
        mock_resp.content = b'fake-mp3'
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {'ELEVENLABS_API_KEY': 'k'}):
            result = async_to_sync(tts_elevenlabs.synthesize)(
                'hello',
                provider_name='elevenlabs',
                provider_config={'voice_id': 'vid123'},
            )
        self.assertTrue(result.success)
        self.assertIsNotNone(result.audio_path)
        self.assertTrue(os.path.isfile(result.audio_path))
        try:
            os.unlink(result.audio_path)
        except OSError:
            pass
