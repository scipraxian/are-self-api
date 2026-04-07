"""Tests for run_gateway management command."""

from io import StringIO
from unittest.mock import AsyncMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase

from talos_gateway.gateway import get_active_gateway_orchestrator


def _close_awaitable_without_running(awaitable):
    """Close a coroutine when ``asyncio.run`` is patched off (avoids RuntimeWarning)."""
    close = getattr(awaitable, 'close', None)
    if callable(close):
        close()


class RunGatewayCommandTests(SimpleTestCase):
    """Smoke tests for ``manage.py run_gateway``."""

    def test_command_invokes_async_main(self):
        """Assert Command.handle runs the async entry via asyncio.run (patched)."""
        with patch(
            'talos_gateway.management.commands.run_gateway.asyncio.run'
        ) as mock_run:
            mock_run.side_effect = _close_awaitable_without_running
            out = StringIO()
            call_command('run_gateway', stdout=out, verbosity=0)
            mock_run.assert_called_once()

    def test_async_main_sets_and_clears_orchestrator(self):
        """Assert run_gateway_main_async clears registry after serve completes."""
        with patch(
            'talos_gateway.management.commands.run_gateway.Server'
        ) as server_cls:
            instance = server_cls.return_value
            instance.serve = AsyncMock(return_value=None)
            from talos_gateway.management.commands.run_gateway import (
                run_gateway_main_async,
            )

            import asyncio

            asyncio.run(run_gateway_main_async())
        self.assertIsNone(get_active_gateway_orchestrator())
