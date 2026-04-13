"""Tests for vocal_auditory_cortex Pydantic contracts."""

from django.test import SimpleTestCase

from vocal_auditory_cortex.contracts import (
    SynthesisResult,
    TranscriptionResult,
    stt_failure_result,
    stt_success_result,
    tts_failure_result,
    tts_success_result,
)


class TranscriptionResultContractTests(SimpleTestCase):
    """Tests for TranscriptionResult shape and helpers."""

    def test_success_round_trip_json(self):
        """Assert model serializes and parses with optional fields omitted."""
        original = stt_success_result(
            'faster_whisper',
            'hello world',
            language='en',
            duration_seconds=1.5,
        )
        payload = original.model_dump()
        restored = TranscriptionResult.model_validate(payload)
        self.assertTrue(restored.success)
        self.assertEqual(restored.text, 'hello world')
        self.assertEqual(restored.provider, 'faster_whisper')
        self.assertEqual(restored.language, 'en')
        self.assertEqual(restored.duration_seconds, 1.5)
        self.assertIsNone(restored.error)

    def test_failure_has_empty_text_and_error(self):
        """Assert STT failure matches Layer 4 semantics (§7.1)."""
        result = stt_failure_result('voxtral', 'binary not found')
        self.assertFalse(result.success)
        self.assertEqual(result.text, '')
        self.assertEqual(result.error, 'binary not found')
        self.assertEqual(result.provider, 'voxtral')


class SynthesisResultContractTests(SimpleTestCase):
    """Tests for SynthesisResult shape and helpers."""

    def test_success_round_trip_json(self):
        """Assert model serializes and parses with optional fields."""
        original = tts_success_result(
            'edge',
            '/tmp/out.mp3',
            format='mp3',
            duration_seconds=2.0,
            voice_name='en-US-AriaNeural',
        )
        payload = original.model_dump()
        restored = SynthesisResult.model_validate(payload)
        self.assertTrue(restored.success)
        self.assertEqual(restored.audio_path, '/tmp/out.mp3')
        self.assertEqual(restored.provider, 'edge')
        self.assertEqual(restored.format, 'mp3')
        self.assertIsNone(restored.error)

    def test_failure_has_no_audio_path_and_error(self):
        """Assert TTS failure matches Layer 4 semantics (§7.1)."""
        result = tts_failure_result('edge', 'network error')
        self.assertFalse(result.success)
        self.assertIsNone(result.audio_path)
        self.assertEqual(result.error, 'network error')
