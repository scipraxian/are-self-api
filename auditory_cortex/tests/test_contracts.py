"""Tests for auditory_cortex Pydantic contracts."""

from django.test import SimpleTestCase

from auditory_cortex.contracts import (
    TranscriptionResult,
    failure_result,
    success_result,
)


class TranscriptionResultContractTests(SimpleTestCase):
    """Tests for TranscriptionResult shape and helpers."""

    def test_success_round_trip_json(self):
        """Assert model serializes and parses with optional fields omitted."""
        original = success_result(
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
        result = failure_result('voxtral', 'binary not found')
        self.assertFalse(result.success)
        self.assertEqual(result.text, '')
        self.assertEqual(result.error, 'binary not found')
        self.assertEqual(result.provider, 'voxtral')
