"""Tests for tts_edge provider."""

from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from vocal_auditory_cortex.providers import tts_edge


class TtsEdgeTests(SimpleTestCase):
    """Tests for Edge TTS provider."""

    @patch('vocal_auditory_cortex.providers.tts_edge.edge_tts', None)
    def test_returns_failure_when_package_missing(self):
        """Assert missing edge_tts yields typed failure."""
        result = async_to_sync(tts_edge.synthesize)(
            'hello',
            provider_name='edge',
            provider_config={'voice': 'en-US-AriaNeural'},
        )
        self.assertFalse(result.success)
        self.assertIn('not installed', result.error or '')

    @patch('vocal_auditory_cortex.providers.tts_edge.edge_tts')
    def test_synthesize_saves_audio(self, mock_edge_mod):
        """Assert Communicate.save is used for output path."""
        comm = MagicMock()
        comm.save = AsyncMock()
        mock_edge_mod.Communicate.return_value = comm

        result = async_to_sync(tts_edge.synthesize)(
            'hello world',
            provider_name='edge',
            provider_config={'voice': 'en-US-AriaNeural'},
        )
        self.assertTrue(result.success)
        self.assertIsNotNone(result.audio_path)
        comm.save.assert_awaited_once()
        mock_edge_mod.Communicate.assert_called_once()
