"""Wiring tests for ``neuroplasticity.boot``.

The destructive logic in ``loader.boot_bundles`` is covered directly in
``test_modifier_lifecycle.py`` under overridden settings. What is NOT
exercised by the rest of the suite is the signal-handler hookup itself —
``schedule_boot`` connecting receivers, ``_on_request_started`` firing
``boot_bundles`` exactly once, and the disconnect-after-fire behavior.
The repo-level ``conftest.py`` sets ``NEUROPLASTICITY_SKIP_BOOT=1`` so
the signal is NOT connected during normal test runs (otherwise the
first ``APIClient`` call in any test rmtree's the real ``grafts/``
dir). These tests opt back in by manually invoking ``schedule_boot``
with ``loader.boot_bundles`` patched out, so nothing touches disk.
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.signals import request_started
from django.test import TestCase

from neuroplasticity import boot


class BootSignalWiringTests(TestCase):
    """Assert ``boot.schedule_boot`` wires the one-shot signal correctly."""

    def setUp(self):
        # _booted is a process-global; reset so each test starts clean.
        boot._booted = False
        # Defensive: ensure no prior receiver is still connected from an
        # earlier test (or stray import). disconnect is no-op on miss.
        try:
            request_started.disconnect(boot._on_request_started)
        except Exception:
            pass

    def tearDown(self):
        try:
            request_started.disconnect(boot._on_request_started)
        except Exception:
            pass
        boot._booted = False

    def test_schedule_boot_fires_boot_bundles_once_on_request(self):
        """Assert boot_bundles fires exactly once when request_started fires."""
        with patch('neuroplasticity.loader.boot_bundles') as mock_boot:
            boot.schedule_boot()
            request_started.send(sender=None)
            request_started.send(sender=None)
            request_started.send(sender=None)
        self.assertEqual(mock_boot.call_count, 1)

    def test_receiver_disconnects_after_first_fire(self):
        """Assert the request_started receiver disconnects after firing once."""
        with patch('neuroplasticity.loader.boot_bundles'):
            boot.schedule_boot()
            request_started.send(sender=None)

        # If the receiver is still connected, disconnect returns True.
        # After the first fire it should already be gone, returning False
        # (or raising — both signal "not connected").
        try:
            still_connected = request_started.disconnect(
                boot._on_request_started
            )
        except Exception:
            still_connected = False
        self.assertFalse(still_connected)

    def test_run_once_is_idempotent_across_calls(self):
        """Assert _run_once short-circuits after the first invocation."""
        with patch('neuroplasticity.loader.boot_bundles') as mock_boot:
            boot._run_once()
            boot._run_once()
            boot._run_once()
        self.assertEqual(mock_boot.call_count, 1)

    def test_boot_bundles_exception_is_swallowed(self):
        """Assert _run_once swallows boot_bundles failures (logs, no raise)."""
        with patch(
            'neuroplasticity.loader.boot_bundles',
            side_effect=RuntimeError('simulated bundle blowup'),
        ):
            # Must not propagate — would otherwise take down the first
            # request that triggers the boot pass.
            boot._run_once()
        # Sanity: the flag still flipped, so no retry storm.
        self.assertTrue(boot._booted)
