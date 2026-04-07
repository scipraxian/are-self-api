"""Tests for stt_faster_whisper provider."""

from unittest.mock import MagicMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from auditory_cortex.providers import stt_faster_whisper


class SttFasterWhisperTests(SimpleTestCase):
    """Tests for faster-whisper provider with mocked model."""

    @patch('auditory_cortex.providers.stt_faster_whisper.WhisperModel', None)
    def test_returns_failure_when_package_missing(self):
        """Assert missing faster_whisper yields typed failure."""
        result = async_to_sync(stt_faster_whisper.transcribe)(
            '/tmp/x.wav',
            provider_name='faster_whisper',
            provider_config={'model': 'base'},
        )
        self.assertFalse(result.success)
        self.assertIn('not installed', result.error or '')

    @patch('auditory_cortex.providers.stt_faster_whisper.WhisperModel')
    def test_transcribe_returns_text_from_segments(self, mock_wm_class):
        """Assert successful path aggregates segment text."""
        segment = MagicMock()
        segment.text = 'hello '
        seg2 = MagicMock()
        seg2.text = 'world'

        model = MagicMock()
        model.transcribe.return_value = ([segment, seg2], MagicMock(language='en', duration=1.2))
        mock_wm_class.return_value = model

        result = async_to_sync(stt_faster_whisper.transcribe)(
            '/tmp/x.wav',
            provider_name='faster_whisper',
            provider_config={
                'model': 'tiny',
                'device': 'cpu',
                'compute_type': 'int8',
            },
        )
        self.assertTrue(result.success)
        self.assertEqual(result.text, 'hello world')
        self.assertEqual(result.language, 'en')
