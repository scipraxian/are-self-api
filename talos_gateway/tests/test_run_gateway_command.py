"""Tests for run_gateway management command."""

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase


class RunGatewayCommandTests(SimpleTestCase):
    """Smoke tests for ``manage.py run_gateway``."""

    def test_command_handle_invokes_asyncio_run(self):
        """Assert Command.handle calls asyncio.run (patched to avoid blocking)."""
        with mock.patch(
            'talos_gateway.management.commands.run_gateway.asyncio.run'
        ) as mock_run:
            mock_run.side_effect = lambda _coro: None
            out = StringIO()
            call_command('run_gateway', stdout=out, verbosity=0)
            mock_run.assert_called_once()
