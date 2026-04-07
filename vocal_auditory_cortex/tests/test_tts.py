"""Tests for vocal_auditory_cortex.tts.TTSService."""

import shutil
import tempfile
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings

from vocal_auditory_cortex.contracts import SynthesisResult, tts_success_result
from vocal_auditory_cortex.tts import TTSService


class TTSServiceTests(SimpleTestCase):
    """Tests for TTS dispatch, cache, errors, and retry policy."""

    def test_synthesize_returns_failure_when_tts_disabled(self):
        """Assert disabled speech stack yields typed failure for TTS."""
        svc = TTSService(
            {
                'enabled': False,
                'tts_provider': 'edge',
                'providers': {},
            }
        )
        result = async_to_sync(svc.synthesize)('hello')
        self.assertFalse(result.success)
        self.assertIsNone(result.audio_path)
        self.assertIn('disabled', (result.error or '').lower())

    def test_synthesize_returns_failure_when_no_provider_configured(self):
        """Assert empty tts_provider is rejected."""
        svc = TTSService({'enabled': True, 'tts_provider': '', 'providers': {}})
        result = async_to_sync(svc.synthesize)('hello')
        self.assertFalse(result.success)
        self.assertIsNone(result.audio_path)

    @patch(
        'vocal_auditory_cortex.tts._call_provider_synthesize',
        new_callable=AsyncMock,
    )
    def test_synthesize_dispatches_to_provider(self, mock_call):
        """Assert configured provider is invoked and success passes through."""
        mock_call.return_value = tts_success_result(
            'edge',
            '/tmp/out.mp3',
            format='mp3',
        )
        svc = TTSService(
            {
                'enabled': True,
                'tts_provider': 'edge',
                'providers': {'edge': {'voice': 'en-US-AriaNeural'}},
            }
        )
        result = async_to_sync(svc.synthesize)('hello world')
        self.assertTrue(result.success)
        self.assertEqual(result.audio_path, '/tmp/out.mp3')
        mock_call.assert_awaited_once()

    @patch(
        'vocal_auditory_cortex.tts._call_provider_synthesize',
        new_callable=AsyncMock,
    )
    @patch('vocal_auditory_cortex.tts.asyncio.sleep', new_callable=AsyncMock)
    def test_remote_provider_retries_once_on_failure(
        self, mock_sleep, mock_call
    ):
        """Assert non-local TTS provider retries once after delay (§7.2)."""
        fail = SynthesisResult(
            success=False,
            audio_path=None,
            provider='edge',
            error='timeout',
        )
        ok = tts_success_result('edge', '/ok.mp3')
        mock_call.side_effect = [fail, ok]

        svc = TTSService(
            {
                'enabled': True,
                'tts_provider': 'edge',
                'providers': {'edge': {}},
            }
        )
        result = async_to_sync(svc.synthesize)('hi')
        self.assertTrue(result.success)
        self.assertEqual(mock_call.await_count, 2)
        mock_sleep.assert_awaited_once_with(2)

    @patch(
        'vocal_auditory_cortex.tts._call_provider_synthesize',
        new_callable=AsyncMock,
    )
    @patch('vocal_auditory_cortex.tts.asyncio.sleep', new_callable=AsyncMock)
    def test_local_voxtral_does_not_retry(self, mock_sleep, mock_call):
        """Assert local voxtral TTS does not retry on failure."""
        fail = SynthesisResult(
            success=False,
            audio_path=None,
            provider='voxtral',
            error='binary missing',
        )
        mock_call.return_value = fail

        svc = TTSService(
            {
                'enabled': True,
                'tts_provider': 'voxtral',
                'providers': {'voxtral': {}},
            }
        )
        result = async_to_sync(svc.synthesize)('hi')
        self.assertFalse(result.success)
        mock_call.assert_awaited_once()
        mock_sleep.assert_not_awaited()

    @patch(
        'vocal_auditory_cortex.tts._call_provider_synthesize',
        new_callable=AsyncMock,
    )
    def test_cache_hit_skips_provider_call(self, mock_call):
        """Assert existing cache file short-circuits synthesis."""
        from vocal_auditory_cortex.tts import _cached_audio_path

        cache_dir = tempfile.mkdtemp()
        try:
            key_path = _cached_audio_path(cache_dir, 'edge', None, 'same text')
            with open(key_path, 'wb') as handle:
                handle.write(b'cached')
            svc = TTSService(
                {
                    'enabled': True,
                    'tts_provider': 'edge',
                    'tts_cache_dir': cache_dir,
                    'providers': {'edge': {}},
                }
            )
            result = async_to_sync(svc.synthesize)('same text')
            self.assertTrue(result.success)
            self.assertEqual(result.audio_path, key_path)
            mock_call.assert_not_awaited()
        finally:
            shutil.rmtree(cache_dir, ignore_errors=True)

    @patch(
        'vocal_auditory_cortex.tts._call_provider_synthesize',
        new_callable=AsyncMock,
    )
    @patch('vocal_auditory_cortex.tts.shutil.copy2')
    def test_success_writes_cache_when_configured(self, mock_copy, mock_call):
        """Assert successful synthesis copies output into tts_cache_dir."""
        mock_call.return_value = tts_success_result(
            'edge', '/src/out.mp3', format='mp3'
        )

        cache_dir = tempfile.mkdtemp()
        try:
            svc = TTSService(
                {
                    'enabled': True,
                    'tts_provider': 'edge',
                    'tts_cache_dir': cache_dir,
                    'providers': {'edge': {}},
                }
            )
            async_to_sync(svc.synthesize)('cache me')
            mock_copy.assert_called_once()
            dest = mock_copy.call_args[0][1]
            self.assertTrue(dest.startswith(cache_dir))
        finally:
            shutil.rmtree(cache_dir, ignore_errors=True)

    @override_settings(
        VOCAL_CORTEX={
            'enabled': True,
            'tts_provider': 'edge',
            'providers': {'edge': {'voice': 'en-US-AriaNeural'}},
        }
    )
    @patch(
        'vocal_auditory_cortex.tts._call_provider_synthesize',
        new_callable=AsyncMock,
    )
    def test_uses_django_settings_when_no_explicit_config(self, mock_call):
        """Assert TTSService reads VOCAL_CORTEX from Django settings."""
        mock_call.return_value = tts_success_result('edge', '/x.mp3')
        svc = TTSService()
        result = async_to_sync(svc.synthesize)('hello')
        self.assertTrue(result.success)
        self.assertEqual(result.audio_path, '/x.mp3')
