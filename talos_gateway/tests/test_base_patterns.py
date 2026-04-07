"""Tests for talos_gateway.adapters.base_patterns."""

from django.test import SimpleTestCase

from talos_gateway.adapters.base_patterns import (
    chunk_text,
    is_likely_audio_mime,
    iter_chunked_payloads,
    truncate_message,
)
from talos_gateway.contracts import DeliveryPayload


class TestChunkText(SimpleTestCase):
    """Tests for chunk_text."""

    def test_chunk_text_splits_long_string(self):
        """Assert text is split into parts at most max_length."""
        text = 'a' * 10
        self.assertEqual(chunk_text(text, 3), ['aaa', 'aaa', 'aaa', 'a'])

    def test_chunk_text_empty_returns_empty_list(self):
        """Assert empty string yields no chunks."""
        self.assertEqual(chunk_text('', 5), [])

    def test_chunk_text_exact_multiple(self):
        """Assert exact boundary produces equal chunks."""
        self.assertEqual(chunk_text('abcdef', 2), ['ab', 'cd', 'ef'])

    def test_chunk_text_rejects_non_positive_max(self):
        """Assert max_length must be positive."""
        with self.assertRaises(ValueError):
            chunk_text('a', 0)
        with self.assertRaises(ValueError):
            chunk_text('a', -1)


class TestIterChunkedPayloads(SimpleTestCase):
    """Tests for iter_chunked_payloads."""

    def test_iter_preserves_platform_and_channel(self):
        """Assert each chunk keeps routing fields."""
        base = DeliveryPayload(
            platform='discord',
            channel_id='c1',
            content='a' * 5,
        )
        chunks = list(iter_chunked_payloads(base, 2))
        self.assertEqual(len(chunks), 3)
        for c in chunks:
            self.assertEqual(c.platform, 'discord')
            self.assertEqual(c.channel_id, 'c1')

    def test_iter_voice_only_on_last_chunk(self):
        """Assert is_voice and voice path attach to last chunk only."""
        p = DeliveryPayload(
            platform='x',
            channel_id='y',
            content='abcd',
            voice_audio_path='/v.mp3',
            is_voice=True,
        )
        chunks = list(iter_chunked_payloads(p, 2))
        self.assertIsNone(chunks[0].voice_audio_path)
        self.assertFalse(chunks[0].is_voice)
        self.assertEqual(chunks[-1].voice_audio_path, '/v.mp3')
        self.assertTrue(chunks[-1].is_voice)


class TestIsLikelyAudioMime(SimpleTestCase):
    """Tests for is_likely_audio_mime."""

    def test_audio_prefix(self):
        """Assert audio/* is detected."""
        self.assertTrue(is_likely_audio_mime('audio/ogg'))

    def test_non_audio(self):
        """Assert image is not audio."""
        self.assertFalse(is_likely_audio_mime('image/png'))


class TestTruncateMessage(SimpleTestCase):
    """Tests for truncate_message."""

    def test_short_message_returns_single_chunk(self):
        """Assert content under max_length is unchanged."""
        self.assertEqual(truncate_message('hello world'), ['hello world'])

    def test_none_chunk_indicator_reserve_does_not_crash(self):
        """Assert explicit None reserve is treated as zero, not a TypeError."""
        body = 'paragraph\n\n' + ('x' * 6000)
        chunks = truncate_message(
            body,
            chunk_indicator_reserve=None,
            max_length=2048,
        )
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(isinstance(c, str) for c in chunks))
