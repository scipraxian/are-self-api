import json
import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

from celery.result import AsyncResult
from django.db import transaction
from django.utils import timezone

from config.celery import app as celery_app
from talos_agent.models import TalosAgentRegistry, TalosAgentStatus

from .models import (
    HydraDistributionModeID,
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpellbook,
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraStatusID,
    HydraWireType,  # <--- Added Import
)
from .tasks import cast_hydra_spell

logger = logging.getLogger(__name__)


class Hydra:
    """
    The High-Level Job Manager (Graph Edition).

    Architecture:
    -------------
    Acts as the Synchronous Orchestrator using 'Database Locking'.

    Graph Logic:
    1. Roots: Spells with no incoming wires start first.
    2. Triggers: When a Head finishes, we check 'HydraSpellbookConnectionWire'.
    3. Provenance: We track the execution history to prevent infinite loops (mostly).
    """

    STALE_PENDING_TIMEOUT = timedelta(minutes=5)

    def __init__(
        self,
        spellbook_id: Optional[uuid.UUID] = None,
        spawn_id: Optional[uuid.UUID] = None,
    ):
        if spawn_id:
            self.spawn = HydraSpawn.objects.get(id=spawn_id)
        elif spellbook_id:
            self.spawn = self._create_spawn(spellbook_id)
        else:
            raise ValueError('Must provide either spawn_id or spellbook_id')

    def start(self) -> None:
        """Ignites the spawn idempotently."""
        with transaction.atomic():
            spawn = HydraSpawn.objects.select_for_update().get(id=self.spawn.id)

            if spawn.status_id != HydraSpawnStatus.CREATED:
                logger.warning(f'[HYDRA] Spawn {spawn.id} already started.')
                return

            spawn.status_id = HydraSpawnStatus.RUNNING
            spawn.save(update_fields=['status'])

        # Dispatch Roots (New Transaction)
        self.dispatch_next_wave()

    def terminate(self) -> None:
        """Aborts the spawn."""
        task_ids_to_revoke = []

        with transaction.atomic():
            spawn = HydraSpawn.objects.select_for_update().get(id=self.spawn.id)

            if spawn.status_id in [
                HydraSpawnStatus.SUCCESS,
                HydraSpawnStatus.FAILED,
            ]:
                return

            running_heads = list(
                spawn.heads.select_for_update().filter(
                    status_id__in=[
                        HydraHeadStatus.RUNNING,
                        HydraHeadStatus.PENDING,
                    ]
                )
            )

            for head in running_heads:
                if head.celery_task_id:
                    task_ids_to_revoke.append(str(head.celery_task_id))

                head.status_id = HydraHeadStatus.ABORTED
                head.execution_log += (
                    '\n[HYDRA] Terminated by User (Signal Sent).\n'
                )
                head.save(update_fields=['status', 'execution_log'])

            spawn.status_id = HydraSpawnStatus.FAILED
            spawn.save(update_fields=['status'])

        for task_id in task_ids_to_revoke:
            try:
                celery_app.control.revoke(task_id, terminate=False)
            except Exception as e:
                logger.warning(f'Failed to revoke task {task_id}: {e}')

        logger.info(f'[HYDRA] Spawn {self.spawn.id} Terminated.')

    def poll(self) -> None:
        """Maintenance Pulse."""
        with transaction.atomic():
            # 1. Ghost Detection
            active_heads = self.spawn.heads.select_for_update().filter(
                status_id=HydraHeadStatus.RUNNING
            )
            for head in active_heads:
                if not head.celery_task_id:
                    continue
                res = AsyncResult(str(head.celery_task_id))
                if res.ready() and res.state in ['FAILURE', 'REVOKED']:
                    logger.warning(f'[HYDRA] Ghost Task {head.id}')
                    head.status_id = HydraHeadStatus.FAILED
                    head.execution_log += (
                        f'\n[HYDRA POLL] Task Crash: {res.info}\n'
                    )
                    head.save(update_fields=['status', 'execution_log'])

            # 2. Stale Pending Detection
            stale_threshold = timezone.now() - self.STALE_PENDING_TIMEOUT
            stale_heads = self.spawn.heads.select_for_update().filter(
                status_id=HydraHeadStatus.PENDING,
                modified__lt=stale_threshold,
            )
            for head in stale_heads:
                head.status_id = HydraHeadStatus.FAILED
                head.execution_log += '\n[HYDRA POLL] Timeout.\n'
                head.save(update_fields=['status', 'execution_log'])

        # 3. Trigger Graph Logic
        self.dispatch_next_wave()

    def view(self) -> Dict[str, Any]:
        """Serializer for UI."""
        # Note: Heads are now ordered by created time since 'order' field is gone
        return {
            'id': str(self.spawn.id),
            'status': self.spawn.status.name,
            'progress': 0.0,  # Progress is hard in a non-linear graph
            'current_wave': 0,
            'heads': [
                {
                    'id': str(h.id),
                    'name': h.spell.talos_executable.name,
                    'node_id': h.node_id if h.node else None,
                    'status_id': h.status.id,
                    'status_name': h.status.name,
                    'log_preview': (h.spell_log or '')[:150],
                }
                for h in self.spawn.heads.all()
                .select_related('spell', 'status', 'node')
                .order_by('created')
            ],
        }

    # =========================================================================
    # Internal Logic
    # =========================================================================

    def _create_spawn(self, spellbook_id: uuid.UUID) -> HydraSpawn:
        book = HydraSpellbook.objects.get(id=spellbook_id)
        # We NO LONGER create heads here. Heads are JIT (Just In Time).
        spawn = HydraSpawn.objects.create(
            spellbook=book,
            status_id=HydraSpawnStatus.CREATED,
            context_data=json.dumps({}),
        )
        self.spawn = spawn
        return spawn

    def dispatch_next_wave(self) -> None:
        """
        Graph Dispatcher:
        1. If no heads exist, launch Roots.
        2. If heads finished, follow Wires.
        """
        with transaction.atomic():
            # Lock rows
            heads = self.spawn.heads.select_for_update().all()

            # 1. Roots Check (First Run)
            if not heads.exists():
                self._dispatch_graph_roots()
                return

            # 2. Trigger Check
            # Find heads that are done (Success/Fail)
            finished_heads = heads.filter(
                status_id__in=[HydraHeadStatus.SUCCESS, HydraHeadStatus.FAILED]
            )

            # Optimization: Filter out heads that have already successfully triggered their children.
            # We look for heads that are listed as 'provenance' in existing heads.
            parents_with_children = HydraHead.objects.filter(
                spawn=self.spawn, provenance__isnull=False
            ).values_list('provenance_id', flat=True)

            for head in finished_heads:
                if head.id in parents_with_children:
                    continue  # Already triggered downstream nodes

                # Check for wires and dispatch
                self._process_graph_triggers(head)

            self._finalize_spawn_unsafe()

    def _dispatch_graph_roots(self) -> None:
        """Execute all Begin Play nodes."""
        all_nodes = self.spawn.spellbook.nodes.all()

        # We filter strictly for the nodes marked is_root in the database/editor
        root_nodes = all_nodes.filter(is_root=True)

        if not root_nodes.exists() and all_nodes.exists():
            logger.error(
                f'[HYDRA] No Begin Play node found '
                f'for {self.spawn.spellbook.name}!'
            )
            return

        for node in root_nodes:
            # Roots have no provenance
            self._create_head_from_node(node, provenance=None)

    def _process_graph_triggers(self, finished_head: HydraHead) -> None:
        """Follows the wires from a finished head based on Status Logic."""
        if not finished_head.node:
            return

        # Determine valid wire types based on the Head's status
        valid_wire_types = []

        # Always trigger "Flow" (White) wires on completion
        valid_wire_types.append(HydraWireType.TYPE_FLOW)

        if finished_head.status_id == HydraHeadStatus.SUCCESS:
            # Success (Green) wires
            valid_wire_types.append(HydraWireType.TYPE_SUCCESS)
        elif finished_head.status_id == HydraHeadStatus.FAILED:
            # Failure (Red) wires
            valid_wire_types.append(HydraWireType.TYPE_FAILURE)

        # Find wires matching the logic
        wires = HydraSpellbookConnectionWire.objects.filter(
            spellbook=self.spawn.spellbook,
            source=finished_head.node,
            type_id__in=valid_wire_types,  # <--- FIXED LOGIC
        )

        if not wires.exists():
            return

        logger.info(
            f'[HYDRA] Triggering {wires.count()} wires from Head {finished_head.id}'
        )

        for wire in wires:
            self._create_head_from_node(
                node=wire.target, provenance=finished_head
            )

    def _create_head_from_node(
        self, node: HydraSpellbookNode, provenance: Optional[HydraHead]
    ):
        """Factory: Creates a head for a specific node."""

        seed_head = HydraHead.objects.create(
            spawn=self.spawn,
            node=node,
            spell=node.spell,  # Denormalized for speed
            provenance=provenance,
            target=None,
            status_id=HydraHeadStatus.CREATED,
        )

        # [DELEGATION PROTOCOL]
        # If this node invokes another Spellbook, we hand off to the GraphWalker
        if node.invoked_spellbook:
            from .engine.graph_walker import GraphWalker

            walker = GraphWalker(spawn_id=self.spawn.id)
            walker.process_node(seed_head)
            return

        # Hand off to specific dispatchers based on mode
        mode = node.spell.distribution_mode_id

        if mode == HydraDistributionModeID.ALL_ONLINE_AGENTS:
            self._dispatch_fleet_wave(seed_head)
        elif mode == HydraDistributionModeID.SPECIFIC_TARGETS:
            self._dispatch_pinned_wave(seed_head)
        elif mode == HydraDistributionModeID.ONE_AVAILABLE_AGENT:
            self._dispatch_first_responder(seed_head)
        else:
            # LOCAL_SERVER (Mode 1): target stays None, runs on local server
            self._prepare_and_dispatch(seed_head)

    def _dispatch_fleet_wave(self, seed_head: HydraHead) -> None:
        """Fans out to all online agents."""
        agents = TalosAgentRegistry.objects.filter(
            status_id=TalosAgentStatus.ONLINE
        )

        if not agents.exists():
            seed_head.status_id = HydraStatusID.FAILED
            seed_head.execution_log = (
                '[HYDRA] No agents online for fleet broadcast.'
            )
            seed_head.save()
            return

        for agent in agents:
            self._clone_and_dispatch_head(seed_head, agent)

        # Seed is just a template, delete it so it doesn't clutter
        seed_head.delete()

    def _dispatch_pinned_wave(self, seed_head: HydraHead) -> None:
        targets = seed_head.spell.specific_targets.all()
        for t in targets:
            self._clone_and_dispatch_head(seed_head, t.target)
        seed_head.delete()

    def _dispatch_first_responder(self, seed_head: HydraHead) -> None:
        agent = (
            TalosAgentRegistry.objects.filter(status_id=TalosAgentStatus.ONLINE)
            .order_by('last_seen')
            .first()
        )

        if not agent:
            seed_head.status_id = HydraStatusID.FAILED
            seed_head.execution_log = '[HYDRA] No agents available.'
            seed_head.save()
            return

        self._clone_and_dispatch_head(seed_head, agent)
        seed_head.delete()

    def _clone_and_dispatch_head(
        self, seed: HydraHead, agent: TalosAgentRegistry
    ):
        new_head = HydraHead.objects.create(
            spawn=seed.spawn,
            node=seed.node,
            spell=seed.spell,
            provenance=seed.provenance,
            target=agent,
            status_id=HydraHeadStatus.PENDING,
        )
        transaction.on_commit(lambda: cast_hydra_spell.delay(new_head.id))

    def _prepare_and_dispatch(self, head: HydraHead) -> None:
        head.status_id = HydraHeadStatus.PENDING
        head.save()
        transaction.on_commit(lambda: cast_hydra_spell.delay(head.id))

    def _finalize_spawn_unsafe(self) -> None:
        """Determines final status."""
        # In a Graph, "Done" means no heads are running/pending
        active = self.spawn.heads.filter(
            status_id__in=[
                HydraHeadStatus.CREATED,
                HydraHeadStatus.PENDING,
                HydraHeadStatus.RUNNING,
                HydraHeadStatus.DELEGATED,
            ]
        )
        if active.exists():
            return

        # If we are here, everything is terminal.
        failed = self.spawn.heads.filter(
            status_id__in=[HydraHeadStatus.FAILED, HydraHeadStatus.ABORTED]
        )

        new_status = (
            HydraSpawnStatus.FAILED
            if failed.exists()
            else HydraSpawnStatus.SUCCESS
        )

        if self.spawn.status_id != new_status:
            self.spawn.status_id = new_status
            self.spawn.save(update_fields=['status'])
            transaction.on_commit(
                lambda: self._trigger_completion_signals(new_status)
            )

    def _trigger_completion_signals(self, status_id: int) -> None:
        from .signals import spawn_failed, spawn_success

        sender = self.spawn.__class__
        if status_id == HydraSpawnStatus.FAILED:
            spawn_failed.send(sender=sender, spawn=self.spawn)
        elif status_id == HydraSpawnStatus.SUCCESS:
            spawn_success.send(sender=sender, spawn=self.spawn)

    # Placeholder for progress
    def _calculate_progress(self) -> float:
        return 0.0
