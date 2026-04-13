"""Tests for vocal_auditory_cortex.stt.STTService."""

from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings

from vocal_auditory_cortex.contracts import TranscriptionResult, stt_success_result
from vocal_auditory_cortex.stt import STTService


class STTServiceTests(SimpleTestCase):
    """Tests for STT dispatch, errors, and retry policy."""

    def test_transcribe_returns_failure_when_stt_disabled(self):
        """Assert disabled speech stack yields typed failure for STT."""
        svc = STTService(
            {
                'enabled': False,
                'stt_provider': 'faster_whisper',
                'providers': {},
            }
        )
        result = async_to_sync(svc.transcribe)('/tmp/a.wav')
        self.assertFalse(result.success)
        self.assertEqual(result.text, '')
        self.assertIn('disabled', (result.error or '').lower())

    def test_transcribe_returns_failure_when_no_provider_configured(self):
        """Assert empty stt_provider is rejected."""
        svc = STTService({'enabled': True, 'stt_provider': '', 'providers': {}})
        result = async_to_sync(svc.transcribe)('/tmp/a.wav')
        self.assertFalse(result.success)
        self.assertEqual(result.text, '')

    @patch(
        'vocal_auditory_cortex.stt._call_provider_transcribe',
        new_callable=AsyncMock,
    )
    def test_transcribe_dispatches_to_provider(self, mock_call):
        """Assert configured provider is invoked and success passes through."""
        mock_call.return_value = stt_success_result(
            'faster_whisper',
            'hello',
            language='en',
        )
        svc = STTService(
            {
                'enabled': True,
                'stt_provider': 'faster_whisper',
                'providers': {'faster_whisper': {'model': 'base'}},
            }
        )
        result = async_to_sync(svc.transcribe)('/tmp/x.wav')
        self.assertTrue(result.success)
        self.assertEqual(result.text, 'hello')
        mock_call.assert_awaited_once()

    @patch(
        'vocal_auditory_cortex.stt._call_provider_transcribe',
        new_callable=AsyncMock,
    )
    @patch('vocal_auditory_cortex.stt.asyncio.sleep', new_callable=AsyncMock)
    def test_remote_provider_retries_once_on_failure(
        self, mock_sleep, mock_call
    ):
        """Assert non-local STT provider retries once after delay (§7.2)."""
        fail = TranscriptionResult(
            success=False,
            text='',
            provider='voxtral',
            error='temporary',
        )
        ok = stt_success_result('voxtral', 'fixed')
        mock_call.side_effect = [fail, ok]

        svc = STTService(
            {
                'enabled': True,
                'stt_provider': 'voxtral',
                'providers': {'voxtral': {}},
            }
        )
        result = async_to_sync(svc.transcribe)('/tmp/x.wav')
        self.assertTrue(result.success)
        self.assertEqual(result.text, 'fixed')
        self.assertEqual(mock_call.await_count, 2)
        mock_sleep.assert_awaited_once_with(2)

    @patch(
        'vocal_auditory_cortex.stt._call_provider_transcribe',
        new_callable=AsyncMock,
    )
    @patch('vocal_auditory_cortex.stt.asyncio.sleep', new_callable=AsyncMock)
    def test_local_faster_whisper_does_not_retry(self, mock_sleep, mock_call):
        """Assert faster_whisper (local) does not retry on failure."""
        fail = TranscriptionResult(
            success=False,
            text='',
            provider='faster_whisper',
            error='model failed',
        )
        mock_call.return_value = fail

        svc = STTService(
            {
                'enabled': True,
                'stt_provider': 'faster_whisper',
                'providers': {'faster_whisper': {'model': 'base'}},
            }
        )
        result = async_to_sync(svc.transcribe)('/tmp/x.wav')
        self.assertFalse(result.success)
        mock_call.assert_awaited_once()
        mock_sleep.assert_not_awaited()

    @patch(
        'vocal_auditory_cortex.stt._call_provider_transcribe',
        new_callable=AsyncMock,
    )
    def test_provider_exception_becomes_typed_failure(self, mock_call):
        """Assert provider RuntimeError maps to failed TranscriptionResult."""
        mock_call.side_effect = RuntimeError('boom')

        svc = STTService(
            {
                'enabled': True,
                'stt_provider': 'faster_whisper',
                'providers': {'faster_whisper': {}},
            }
        )
        result = async_to_sync(svc.transcribe)('/tmp/x.wav')
        self.assertFalse(result.success)
        self.assertEqual(result.text, '')
        self.assertIn('boom', result.error or '')

    @override_settings(
        VOCAL_CORTEX={
            'enabled': True,
            'stt_provider': 'faster_whisper',
            'providers': {'faster_whisper': {'model': 'base'}},
        }
    )
    @patch(
        'vocal_auditory_cortex.stt._call_provider_transcribe',
        new_callable=AsyncMock,
    )
    def test_uses_django_settings_when_no_explicit_config(self, mock_call):
        """Assert STTService reads VOCAL_CORTEX from Django settings."""
        mock_call.return_value = stt_success_result('faster_whisper', 'ok')
        svc = STTService()
        result = async_to_sync(svc.transcribe)('/tmp/x.wav')
        self.assertTrue(result.success)
        self.assertEqual(result.text, 'ok')
