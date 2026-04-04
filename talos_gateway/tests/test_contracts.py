"""Tests for talos_gateway Pydantic contracts."""

import base64
import json
from datetime import datetime, timezone

from django.test import SimpleTestCase

from talos_gateway.contracts import Attachment, DeliveryPayload, PlatformEnvelope


class TestAttachment(SimpleTestCase):
    """Tests for Attachment."""

    def test_attachment_round_trip(self):
        """Assert Attachment serializes and validates with optional size_bytes."""
        original = Attachment(
            url='https://example.com/f.png',
            filename='f.png',
            content_type='image/png',
            size_bytes=1024,
        )
        dumped = original.model_dump()
        restored = Attachment.model_validate(dumped)
        self.assertEqual(restored, original)

    def test_attachment_without_size(self):
        """Assert size_bytes may be omitted."""
        a = Attachment(
            url='https://x.com/a',
            filename='a',
            content_type='application/octet-stream',
        )
        # By default None
        self.assertIsNone(a.size_bytes)


class TestPlatformEnvelope(SimpleTestCase):
    """Tests for PlatformEnvelope."""

    def test_platform_envelope_minimal_round_trip(self):
        """Assert required fields round-trip through model_dump and validate."""
        ts = datetime(2026, 4, 3, 12, 0, 0, tzinfo=timezone.utc)
        env = PlatformEnvelope(
            platform='discord',
            channel_id='ch1',
            sender_id='u1',
            sender_name='User',
            message_id='m1',
            content='hello',
            timestamp=ts,
        )
        data = env.model_dump()
        again = PlatformEnvelope.model_validate(data)
        self.assertEqual(again.content, 'hello')
        self.assertIsNone(again.thread_id)
        self.assertEqual(again.attachments, [])

    def test_platform_envelope_empty_content_allowed(self):
        """Assert content may be empty for voice-only paths."""
        ts = datetime.now(timezone.utc)
        env = PlatformEnvelope(
            platform='cli',
            channel_id='local',
            sender_id='cli',
            sender_name='CLI',
            message_id='0',
            content='',
            timestamp=ts,
        )
        self.assertEqual(env.content, '')

    def test_platform_envelope_with_attachments(self):
        """Assert nested attachments validate."""
        ts = datetime.now(timezone.utc)
        env = PlatformEnvelope(
            platform='discord',
            channel_id='c',
            sender_id='s',
            sender_name='n',
            message_id='mid',
            content='see file',
            attachments=[
                Attachment(
                    url='https://cdn/x.png',
                    filename='x.png',
                    content_type='image/png',
                )
            ],
            timestamp=ts,
        )
        self.assertEqual(len(env.attachments), 1)
        self.assertEqual(env.attachments[0].filename, 'x.png')

    def test_platform_envelope_voice_json_uses_base64(self):
        """Assert voice_audio round-trips through JSON as base64."""
        ts = datetime.now(timezone.utc)
        raw = b'\x00\xff\x01'
        env = PlatformEnvelope(
            platform='discord',
            channel_id='c',
            sender_id='s',
            sender_name='n',
            message_id='m',
            content='',
            voice_audio=raw,
            timestamp=ts,
        )
        payload = json.loads(env.model_dump_json())
        self.assertEqual(
            payload['voice_audio'],
            base64.b64encode(raw).decode('ascii'),
        )


class TestDeliveryPayload(SimpleTestCase):
    """Tests for DeliveryPayload."""

    def test_delivery_payload_defaults(self):
        """Assert defaults for optional collections and flags."""
        p = DeliveryPayload(
            platform='discord',
            channel_id='c1',
            content='hi',
        )
        self.assertEqual(p.media_paths, [])
        self.assertIsNone(p.voice_audio_path)
        self.assertFalse(p.is_voice)

    def test_delivery_payload_voice_fields(self):
        """Assert voice path and is_voice are preserved."""
        p = DeliveryPayload(
            platform='discord',
            channel_id='c',
            content='spoken text',
            voice_audio_path='/tmp/out.mp3',
            is_voice=True,
        )
        again = DeliveryPayload.model_validate(p.model_dump())
        self.assertEqual(again.voice_audio_path, '/tmp/out.mp3')
        self.assertTrue(again.is_voice)
