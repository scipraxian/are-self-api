"""Unit tests for talos_gateway.ws_protocol."""

from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from talos_gateway.ws_protocol import (
    WS_MSG_INBOUND,
    platform_envelope_from_inbound_payload,
)


class PlatformEnvelopeFromInboundPayloadTests(SimpleTestCase):
    """Tests for ``platform_envelope_from_inbound_payload``."""

    def test_minimal_inbound_builds_cli_envelope(self):
        """Assert required fields produce a cli ``PlatformEnvelope``."""
        frozen = datetime(2026, 4, 6, 15, 0, 0, tzinfo=timezone.utc)
        with patch(
            'talos_gateway.ws_protocol.timezone.now', return_value=frozen
        ):
            env = platform_envelope_from_inbound_payload(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'ch-a',
                    'message_id': 'mid-9',
                    'content': 'hello',
                }
            )
        self.assertEqual(env.platform, 'cli')
        self.assertEqual(env.channel_id, 'ch-a')
        self.assertEqual(env.message_id, 'mid-9')
        self.assertEqual(env.content, 'hello')
        self.assertEqual(env.sender_id, 'cli')
        self.assertEqual(env.sender_name, 'CLI')
        self.assertEqual(env.timestamp, frozen)

    def test_wrong_type_raises(self):
        """Assert non-inbound type is rejected."""
        with self.assertRaises(ValueError) as ctx:
            platform_envelope_from_inbound_payload(
                {
                    'type': 'ping',
                    'channel_id': 'c',
                    'message_id': '1',
                    'content': 'x',
                }
            )
        self.assertIn('inbound', str(ctx.exception).lower())

    def test_numeric_message_id_stringified(self):
        """Assert message_id may be numeric and is coerced to str."""
        with patch('talos_gateway.ws_protocol.timezone.now'):
            env = platform_envelope_from_inbound_payload(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'c',
                    'message_id': 42,
                    'content': '',
                }
            )
        self.assertEqual(env.message_id, '42')

    def test_identity_disc_id_parsed_when_present(self):
        """Assert identity_disc_id string is preserved on the envelope."""
        with patch('talos_gateway.ws_protocol.timezone.now'):
            env = platform_envelope_from_inbound_payload(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'c',
                    'message_id': '1',
                    'content': 'x',
                    'identity_disc_id': 'disc-uuid-123',
                }
            )
        self.assertEqual(env.identity_disc_id, 'disc-uuid-123')

    def test_identity_disc_id_defaults_to_none_when_omitted(self):
        """Assert envelope.identity_disc_id is None when key is absent."""
        with patch('talos_gateway.ws_protocol.timezone.now'):
            env = platform_envelope_from_inbound_payload(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'c',
                    'message_id': '1',
                    'content': 'x',
                }
            )
        self.assertIsNone(env.identity_disc_id)

    def test_identity_disc_id_null_treated_as_none(self):
        """Assert explicit null identity_disc_id resolves to None."""
        with patch('talos_gateway.ws_protocol.timezone.now'):
            env = platform_envelope_from_inbound_payload(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'c',
                    'message_id': '1',
                    'content': 'x',
                    'identity_disc_id': None,
                }
            )
        self.assertIsNone(env.identity_disc_id)

    def test_identity_disc_id_empty_string_treated_as_none(self):
        """Assert empty identity_disc_id is normalized to None."""
        with patch('talos_gateway.ws_protocol.timezone.now'):
            env = platform_envelope_from_inbound_payload(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'c',
                    'message_id': '1',
                    'content': 'x',
                    'identity_disc_id': '',
                }
            )
        self.assertIsNone(env.identity_disc_id)

    def test_identity_disc_id_non_string_raises(self):
        """Assert non-string identity_disc_id is rejected."""
        with self.assertRaises(ValueError) as ctx:
            platform_envelope_from_inbound_payload(
                {
                    'type': WS_MSG_INBOUND,
                    'channel_id': 'c',
                    'message_id': '1',
                    'content': 'x',
                    'identity_disc_id': 123,
                }
            )
        self.assertIn('identity_disc_id', str(ctx.exception))
