"""Tests for talos_gateway.cli.display — pure rendering and input parsing."""

from django.test import SimpleTestCase

from talos_gateway.cli.display import (
    format_error,
    format_response_complete,
    format_session_info,
    format_session_list,
    format_token_delta,
    parse_cli_input,
    print_welcome,
)


class ParseCliInputTests(SimpleTestCase):
    """Tests for ``parse_cli_input``."""

    def test_parse_cli_input_plain_text(self):
        """Assert plain text returns ('message', 'hello world')."""
        cmd, args = parse_cli_input('hello world')
        self.assertEqual(cmd, 'message')
        self.assertEqual(args, 'hello world')

    def test_parse_cli_input_command(self):
        """Assert '/new' returns ('new', '')."""
        cmd, args = parse_cli_input('/new')
        self.assertEqual(cmd, 'new')
        self.assertEqual(args, '')

    def test_parse_cli_input_command_with_args(self):
        """Assert '/select abc-123' returns ('select', 'abc-123')."""
        cmd, args = parse_cli_input('/select abc-123')
        self.assertEqual(cmd, 'select')
        self.assertEqual(args, 'abc-123')

    def test_parse_cli_input_attach_with_path(self):
        """Assert '/attach /tmp/file.txt' returns ('attach', '/tmp/file.txt')."""
        cmd, args = parse_cli_input('/attach /tmp/file.txt')
        self.assertEqual(cmd, 'attach')
        self.assertEqual(args, '/tmp/file.txt')

    def test_parse_cli_input_interrupt(self):
        """Assert '/interrupt' returns ('interrupt', '')."""
        cmd, args = parse_cli_input('/interrupt')
        self.assertEqual(cmd, 'interrupt')
        self.assertEqual(args, '')

    def test_parse_cli_input_voice(self):
        """Assert '/voice' returns ('voice', '')."""
        cmd, args = parse_cli_input('/voice')
        self.assertEqual(cmd, 'voice')
        self.assertEqual(args, '')


class FormatFunctionTests(SimpleTestCase):
    """Tests for display formatting functions."""

    def test_format_session_list_empty(self):
        """Assert empty list returns 'No active sessions.' message."""
        result = format_session_list([])
        self.assertIn('No active sessions', result)

    def test_format_session_list_with_sessions(self):
        """Assert formatted output contains session IDs and channel info."""
        sessions = [
            {
                'session_id': 'abc-123',
                'channel_id': 'chan-1',
                'status': '1',
                'last_activity': '2026-04-13T10:00:00',
                'identity_disc_name': 'Julianna',
            },
        ]
        result = format_session_list(sessions)
        self.assertIn('abc-123', result)
        self.assertIn('chan-1', result)
        self.assertIn('Julianna', result)

    def test_format_session_info(self):
        """Assert session summary includes ID, status, and identity name."""
        result = format_session_info('abc-123', 'active', 'Julianna')
        self.assertIn('abc-123', result)
        self.assertIn('active', result)
        self.assertIn('Julianna', result)

    def test_format_error(self):
        """Assert error code and message are present in output."""
        result = format_error('gateway_unavailable', 'orchestrator not running')
        self.assertIn('gateway_unavailable', result)
        self.assertIn('orchestrator not running', result)

    def test_print_welcome_contains_commands(self):
        """Assert welcome banner includes /new, /sessions, /quit."""
        result = print_welcome()
        self.assertIn('/new', result)
        self.assertIn('/sessions', result)
        self.assertIn('/quit', result)
