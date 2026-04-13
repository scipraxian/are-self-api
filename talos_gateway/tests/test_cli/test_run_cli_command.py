"""Tests for talos_gateway.management.commands.run_cli."""

from django.core.management import get_commands, load_command_class
from django.test import SimpleTestCase


class RunCliCommandTests(SimpleTestCase):
    """Tests for the ``run_cli`` management command definition."""

    def test_command_has_expected_arguments(self):
        """Assert --host, --port, --channel, --session arguments exist."""
        cmd = load_command_class('talos_gateway', 'run_cli')
        parser = cmd.create_parser('manage.py', 'run_cli')
        actions = {a.dest for a in parser._actions}
        for expected in ('host', 'port', 'channel', 'session'):
            self.assertIn(expected, actions)

    def test_command_default_values(self):
        """Assert default host/port/channel values are sensible."""
        cmd = load_command_class('talos_gateway', 'run_cli')
        parser = cmd.create_parser('manage.py', 'run_cli')
        defaults = parser.parse_args([])
        self.assertEqual(defaults.host, '127.0.0.1')
        self.assertEqual(defaults.port, 8001)
        self.assertEqual(defaults.channel, 'cli-default')
        self.assertIsNone(defaults.session)
