"""Tests for vocal_cortex Pydantic contracts."""

from django.test import SimpleTestCase

from vocal_cortex.contracts import (
    SynthesisResult,
    failure_result,
    success_result,
)


class SynthesisResultContractTests(SimpleTestCase):
    """Tests for SynthesisResult shape and helpers."""

    def test_success_round_trip_json(self):
        """Assert model serializes and parses with optional fields."""
        original = success_result(
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
        result = failure_result('edge', 'network error')
        self.assertFalse(result.success)
        self.assertIsNone(result.audio_path)
        self.assertEqual(result.error, 'network error')
