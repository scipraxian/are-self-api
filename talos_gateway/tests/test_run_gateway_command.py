"""Tests for run_gateway management command."""

from io import StringIO
from unittest.mock import AsyncMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase

from talos_gateway.gateway import get_active_gateway_orchestrator


def _close_awaitable_without_running(awaitable):
    """Close coroutine when patched asyncio.run avoids running it."""
    close = getattr(awaitable, 'close', None)
    if callable(close):
        close()


class RunGatewayCommandTests(SimpleTestCase):
    """Smoke tests for ``manage.py run_gateway``."""

    def test_command_invokes_async_main(self):
        """Assert handle runs async entry via patched ``asyncio.run``."""
        with patch(
            'talos_gateway.management.commands.run_gateway.asyncio.run'
        ) as mock_run:
            mock_run.side_effect = _close_awaitable_without_running
            out = StringIO()
            call_command('run_gateway', stdout=out, verbosity=0)
            mock_run.assert_called_once()

    def test_async_main_sets_and_clears_orchestrator(self):
        """Assert ``run_gateway_main_async`` clears orchestrator after serve."""
        with patch(
            'talos_gateway.management.commands.run_gateway.Server'
        ) as server_cls:
            instance = server_cls.return_value
            instance.serve = AsyncMock(return_value=None)
            import asyncio

            from talos_gateway.management.commands.run_gateway import (
                run_gateway_main_async,
            )

            asyncio.run(run_gateway_main_async())
        self.assertIsNone(get_active_gateway_orchestrator())
