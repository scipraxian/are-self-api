"""Tests for talos_gateway.management.commands.run_cli."""

import io
from unittest.mock import patch

from django.core.management import call_command, load_command_class
from django.test import SimpleTestCase

from common.tests.common_test_case import CommonFixturesAPITestCase


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
        self.assertTrue(defaults.channel.startswith('cli-'))
        self.assertIsNone(defaults.session)

    def test_command_has_identity_disc_arguments(self):
        """Assert --identity-disc and --list-identity-discs arguments exist."""
        cmd = load_command_class('talos_gateway', 'run_cli')
        parser = cmd.create_parser('manage.py', 'run_cli')
        actions = {a.dest for a in parser._actions}
        self.assertIn('identity_disc', actions)
        self.assertIn('list_identity_discs', actions)

    def test_identity_disc_default_is_none(self):
        """Assert --identity-disc defaults to None."""
        cmd = load_command_class('talos_gateway', 'run_cli')
        parser = cmd.create_parser('manage.py', 'run_cli')
        defaults = parser.parse_args([])
        self.assertIsNone(defaults.identity_disc)
        self.assertFalse(defaults.list_identity_discs)

    def test_identity_disc_value_parsed(self):
        """Assert --identity-disc captures the supplied UUID string."""
        cmd = load_command_class('talos_gateway', 'run_cli')
        parser = cmd.create_parser('manage.py', 'run_cli')
        parsed = parser.parse_args([
            '--identity-disc', '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838',
        ])
        self.assertEqual(
            parsed.identity_disc,
            '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838',
        )

    def test_identity_disc_forwarded_to_run_cli_main_async(self):
        """Assert --identity-disc forwards to run_cli_main_async."""
        captured: dict = {}

        async def _fake_main(**kwargs):
            captured.update(kwargs)

        # Patch run_cli_main_async so we never hit the network.
        with patch(
            'talos_gateway.management.commands.run_cli.run_cli_main_async',
            _fake_main,
        ):
            call_command(
                'run_cli',
                '--identity-disc', '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838',
                '--host', '127.0.0.1',
                '--port', '8001',
                '--channel', 'cli-test',
            )

        self.assertEqual(
            captured.get('identity_disc_id'),
            '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838',
        )

    def test_default_identity_disc_id_is_none(self):
        """Assert run_cli forwards None for identity_disc_id by default."""
        captured: dict = {}

        async def _fake_main(**kwargs):
            captured.update(kwargs)

        with patch(
            'talos_gateway.management.commands.run_cli.run_cli_main_async',
            _fake_main,
        ):
            call_command(
                'run_cli',
                '--host', '127.0.0.1',
                '--port', '8001',
                '--channel', 'cli-default-test',
            )

        self.assertIsNone(captured.get('identity_disc_id'))


class RunCliListIdentityDiscsTests(CommonFixturesAPITestCase):
    """``--list-identity-discs`` prints discs and exits without connecting."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'identity/fixtures/identity_discs.json',
    ]

    def test_list_identity_discs_prints_available_and_skips_connect(self):
        """Assert --list-identity-discs prints discs without spawning the client."""
        out = io.StringIO()
        called = {'main': False}

        async def _should_not_run(**_kwargs):
            called['main'] = True

        with patch(
            'talos_gateway.management.commands.run_cli.run_cli_main_async',
            _should_not_run,
        ):
            call_command(
                'run_cli', '--list-identity-discs', stdout=out,
            )

        text = out.getvalue()
        self.assertFalse(called['main'])
        self.assertIn('Thalamus', text)
        # The required THALAMUS UUID must surface in the listing.
        self.assertIn('15ca85b8-59a9-4cb6-9fd8-bfd2be47b838', text)
