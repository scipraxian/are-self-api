"""Tests for the ONLINE/OFFLINE reconcile flow in _run_async_scan.

These cover the bug where the PNS dashboard kept showing terminals as ONLINE
after they went away: scans only ever registered the found set and never
flipped the missing ones OFFLINE. They also lock in the second-generation
fix: the scan writes to the DB only on real transitions (no CHECKING
transient, and no ONLINE-over-ONLINE no-op saves) so that dendrite
broadcasts stop storming the frontend.

The tests deliberately do not touch the real network — _probe_agent is
mocked so we can exercise the reconcile logic deterministically.
"""

import uuid
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.utils import timezone

from common.tests.common_test_case import CommonTestCase
from peripheral_nervous_system.models import (
    NerveTerminalRegistry,
    NerveTerminalStatus,
)
from peripheral_nervous_system.peripheral_nervous_system import (
    AgentIdentity,
    _run_async_scan,
)


def _make_terminal(hostname, status_id, *, ip='192.168.1.10', last_seen=None):
    return NerveTerminalRegistry.objects.create(
        id=uuid.uuid4(),
        hostname=hostname,
        ip_address=ip,
        port=5005,
        version='1.0.0',
        status_id=status_id,
        last_seen=last_seen or timezone.now(),
    )


class ScanReconcileTests(CommonTestCase):
    """Verify _run_async_scan correctly reconciles registry state."""

    fixtures = (
        'initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
    )

    def _patch_probes(self, identities):
        """Patch _probe_agent so gather() yields exactly `identities` once.

        identities is a list of AgentIdentity (or None) to dole out in
        order of call. Probes past the end return None (host unreachable).
        """
        call_iter = iter(identities)

        async def fake_probe(ip, port):
            try:
                return next(call_iter)
            except StopIteration:
                return None

        return patch(
            'peripheral_nervous_system.peripheral_nervous_system._probe_agent',
            new=AsyncMock(side_effect=fake_probe),
        )

    def test_found_agent_becomes_online(self):
        """An agent that PONGs ends up ONLINE with last_seen stamped."""
        agent_id = str(uuid.uuid4())
        identity = AgentIdentity(
            unique_id=agent_id,
            ip_address='192.168.1.42',
            hostname='Returning.Agent',
            version='1.2.3',
        )

        with self._patch_probes([identity]):
            async_to_sync(_run_async_scan)('192.168.1.', 5005)

        row = NerveTerminalRegistry.objects.get(id=agent_id)
        self.assertEqual(row.status_id, NerveTerminalStatus.ONLINE)
        self.assertEqual(row.hostname, 'RETURNING')
        self.assertIsNotNone(row.last_seen)

    def test_missing_agent_transitions_online_to_offline(self):
        """
        The core bug fix: a previously-ONLINE terminal that no longer
        responds gets flipped to OFFLINE at the end of the scan.
        """
        stale = _make_terminal(
            'Ghost.Agent', NerveTerminalStatus.ONLINE, ip='192.168.1.77'
        )

        # No probes succeed — nobody is home.
        with self._patch_probes([]):
            async_to_sync(_run_async_scan)('192.168.1.', 5005)

        stale.refresh_from_db()
        self.assertEqual(stale.status_id, NerveTerminalStatus.OFFLINE)

    def test_found_and_missing_resolved_independently(self):
        """Mixed scan: one PONG, one ghost. The PONG stays ONLINE, the
        ghost moves to OFFLINE, and they don't interfere with each other.
        """
        # Pre-seed one stale terminal and one that will respond.
        responding_id = str(uuid.uuid4())
        responder = _make_terminal(
            'Responder',
            NerveTerminalStatus.ONLINE,
            ip='192.168.1.10',
        )
        # Force the pk to match what the scan will upsert against.
        NerveTerminalRegistry.objects.filter(pk=responder.pk).update(
            id=responding_id
        )

        ghost = _make_terminal(
            'Ghost', NerveTerminalStatus.ONLINE, ip='192.168.1.99'
        )

        identity = AgentIdentity(
            unique_id=responding_id,
            ip_address='192.168.1.10',
            hostname='Responder',
            version='1.0.0',
        )
        with self._patch_probes([identity]):
            async_to_sync(_run_async_scan)('192.168.1.', 5005)

        responder_row = NerveTerminalRegistry.objects.get(id=responding_id)
        ghost.refresh_from_db()

        self.assertEqual(
            responder_row.status_id, NerveTerminalStatus.ONLINE
        )
        self.assertEqual(ghost.status_id, NerveTerminalStatus.OFFLINE)

    def test_already_offline_terminal_is_not_touched(self):
        """A terminal that was already OFFLINE before the scan should
        not be re-saved. We assert that its `modified` timestamp does
        not change across the scan."""
        row = _make_terminal(
            'Longtime.Ghost',
            NerveTerminalStatus.OFFLINE,
            ip='192.168.1.200',
        )
        original_modified = row.modified

        with self._patch_probes([]):
            async_to_sync(_run_async_scan)('192.168.1.', 5005)

        row.refresh_from_db()
        self.assertEqual(row.status_id, NerveTerminalStatus.OFFLINE)
        self.assertEqual(row.modified, original_modified)

    def test_checking_is_never_written_by_scan(self):
        """The scan must NEVER write a CHECKING row. The old flow flipped
        every live terminal to CHECKING as a UI hint, but that per-row
        .save() produced an acetylcholine broadcast storm that made the
        dashboard churn. The scan now goes straight to the terminal state
        (ONLINE or OFFLINE) and writes only on real transitions.
        """
        _make_terminal('Alpha', NerveTerminalStatus.ONLINE, ip='192.168.1.1')
        _make_terminal('Beta', NerveTerminalStatus.ONLINE, ip='192.168.1.2')
        _make_terminal('Gamma', NerveTerminalStatus.OFFLINE, ip='192.168.1.3')

        with self._patch_probes([]):
            async_to_sync(_run_async_scan)('192.168.1.', 5005)

        self.assertFalse(
            NerveTerminalRegistry.objects.filter(
                status_id=NerveTerminalStatus.CHECKING
            ).exists()
        )

    def test_register_is_noop_save_when_nothing_changed(self):
        """A stable agent that PONGs with identical (status, ip, version)
        must not be re-saved. The whole point of compare-then-save is to
        kill the ONLINE-over-ONLINE broadcast storm that was re-firing
        acetylcholine on every scan cycle."""
        from peripheral_nervous_system import peripheral_nervous_system as pns

        agent_id = str(uuid.uuid4())
        # Pre-seed exactly what a probe would produce.
        NerveTerminalRegistry.objects.create(
            id=agent_id,
            hostname='STABLE',
            ip_address='192.168.1.50',
            port=5005,
            version='2.0.0',
            status_id=NerveTerminalStatus.ONLINE,
        )
        original_modified = NerveTerminalRegistry.objects.get(
            id=agent_id
        ).modified

        identity = AgentIdentity(
            unique_id=agent_id,
            ip_address='192.168.1.50',
            hostname='Stable',
            version='2.0.0',
        )
        with self._patch_probes([identity]):
            async_to_sync(_run_async_scan)('192.168.1.', 5005)

        row = NerveTerminalRegistry.objects.get(id=agent_id)
        # Status unchanged and -- crucially -- modified timestamp is
        # untouched, which is our proxy for "no .save() happened".
        self.assertEqual(row.status_id, NerveTerminalStatus.ONLINE)
        self.assertEqual(row.modified, original_modified)

    def test_register_saves_when_version_changes(self):
        """If a discovered agent reports a new version the row must
        be updated and saved -- compare-then-save is change-aware, not
        blanket-skip."""
        agent_id = str(uuid.uuid4())
        NerveTerminalRegistry.objects.create(
            id=agent_id,
            hostname='UPGRADER',
            ip_address='192.168.1.60',
            port=5005,
            version='1.0.0',
            status_id=NerveTerminalStatus.ONLINE,
        )

        identity = AgentIdentity(
            unique_id=agent_id,
            ip_address='192.168.1.60',
            hostname='Upgrader',
            version='1.1.0',
        )
        with self._patch_probes([identity]):
            async_to_sync(_run_async_scan)('192.168.1.', 5005)

        row = NerveTerminalRegistry.objects.get(id=agent_id)
        self.assertEqual(row.version, '1.1.0')
        self.assertEqual(row.status_id, NerveTerminalStatus.ONLINE)

    def test_register_saves_when_bringing_offline_back_online(self):
        """An OFFLINE agent that pongs must be flipped to ONLINE even
        if ip and version happen to match the old row."""
        agent_id = str(uuid.uuid4())
        NerveTerminalRegistry.objects.create(
            id=agent_id,
            hostname='RETURNED',
            ip_address='192.168.1.70',
            port=5005,
            version='1.0.0',
            status_id=NerveTerminalStatus.OFFLINE,
        )

        identity = AgentIdentity(
            unique_id=agent_id,
            ip_address='192.168.1.70',
            hostname='Returned',
            version='1.0.0',
        )
        with self._patch_probes([identity]):
            async_to_sync(_run_async_scan)('192.168.1.', 5005)

        row = NerveTerminalRegistry.objects.get(id=agent_id)
        self.assertEqual(row.status_id, NerveTerminalStatus.ONLINE)

    def test_concurrent_scan_is_skipped(self):
        """Re-entering _run_async_scan while one is already running
        should return immediately with an empty list and leave the
        registry untouched."""
        import asyncio

        from peripheral_nervous_system import peripheral_nervous_system as pns

        _make_terminal(
            'Lockable', NerveTerminalStatus.ONLINE, ip='192.168.1.5'
        )

        async def scenario():
            # Acquire the lock to simulate "a scan is already running".
            async with pns._SCAN_LOCK:
                result = await pns._run_async_scan('192.168.1.', 5005)
            return result

        result = async_to_sync(scenario)()

        # The re-entrant call should have bailed out.
        self.assertEqual(result, [])

        # And it should NOT have touched the existing row. (Raw-ORM
        # creation preserves the original casing; only the scan's
        # registrar uppercases.)
        row = NerveTerminalRegistry.objects.get(hostname='Lockable')
        self.assertEqual(row.status_id, NerveTerminalStatus.ONLINE)


class NerveTerminalRegistryListTests(CommonTestCase):
    """Verify GET /api/v2/nerve_terminal_registry/ triggers a reconcile scan.

    list() kicks a scan for page-load freshness -- hitting the PNS page
    in the UI should immediately discover new agents and retire dead
    ones without the user clicking "Scan". The storm that this coupling
    used to cause is prevented further down the stack: compare-then-save
    in the registrar + no CHECKING transient means a stable fleet
    produces zero broadcasts, so the scan->broadcast->refetch->scan loop
    terminates on its own after one real state change.
    """

    fixtures = (
        'initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
    )

    def test_list_triggers_scan_and_returns_reconciled_state(self):
        """A ghost terminal should be OFFLINE in the list response after
        GET, because list() kicks a scan that finds nothing."""
        ghost = _make_terminal(
            'Ghost.On.List',
            NerveTerminalStatus.ONLINE,
            ip='192.168.1.88',
        )

        with patch(
            'peripheral_nervous_system.peripheral_nervous_system._probe_agent',
            new=AsyncMock(return_value=None),
        ):
            response = self.test_client.get(
                '/api/v2/nerve_terminal_registry/'
            )

        self.assertEqual(response.status_code, 200)
        ghost.refresh_from_db()
        self.assertEqual(ghost.status_id, NerveTerminalStatus.OFFLINE)

        hostnames = [row['hostname'] for row in response.json()]
        self.assertIn('Ghost.On.List', hostnames)

    def test_list_is_resilient_to_scan_failures(self):
        """If the scan blows up, list() still returns the current DB
        state rather than 500ing."""
        _make_terminal(
            'Survivor', NerveTerminalStatus.ONLINE, ip='192.168.1.11'
        )

        with patch(
            'peripheral_nervous_system.api._run_async_scan',
            new=AsyncMock(side_effect=RuntimeError('boom')),
        ):
            response = self.test_client.get(
                '/api/v2/nerve_terminal_registry/'
            )

        self.assertEqual(response.status_code, 200)
        hostnames = [row['hostname'] for row in response.json()]
        self.assertIn('Survivor', hostnames)
