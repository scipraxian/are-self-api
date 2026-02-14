import json
import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

from celery.result import AsyncResult
from django.db import transaction
from django.utils import timezone

from config.celery import app as celery_app
from environments.models import ProjectEnvironment
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
    HydraWireType,
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

        self.dispatch_next_wave()

    def terminate(self) -> None:
        """Aborts the spawn immediately (Hard Kill)."""
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

    def stop_gracefully(self) -> None:
        """
        Signals active heads to stop gracefully.
        Sets status to STOPPING.
        """

        with transaction.atomic():
            spawn = HydraSpawn.objects.select_for_update().get(id=self.spawn.id)

            active_heads = spawn.heads.select_for_update().filter(
                status_id__in=[
                    HydraHeadStatus.RUNNING,
                    HydraHeadStatus.PENDING,
                ]
            )

            count = active_heads.update(
                status_id=HydraHeadStatus.STOPPING, modified=timezone.now()
            )

            if count > 0:
                spawn.status_id = HydraSpawnStatus.STOPPING
                spawn.save(update_fields=['status'])

            logger.info(
                f'[HYDRA] Spawn {self.spawn.id}: '
                f'stop_gracefully signaled {count} heads.'
            )

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
        return {
            'id': str(self.spawn.id),
            'status': self.spawn.status.name,
            'progress': 0.0,
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
        active_env = ProjectEnvironment.objects.filter(selected=True).first()
        spawn = HydraSpawn.objects.create(
            spellbook=book,
            status_id=HydraSpawnStatus.CREATED,
            context_data=json.dumps({}),
            environment=active_env,
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
            # Refresh to ensure we catch STOPPING state updates
            self.spawn.refresh_from_db()

            if self.spawn.status_id == HydraSpawnStatus.STOPPING:
                logger.info(
                    f'[HYDRA] Spawn {self.spawn.id} is STOPPING. Halting graph traversal.'
                )
                self._finalize_spawn_unsafe()
                return

            heads = self.spawn.heads.select_for_update().all()

            if not heads.exists():
                self._dispatch_graph_roots()
                return

            # Trigger Check: Include STOPPED as a terminal state that might allow flow (e.g. Failure paths)
            # Depending on desired logic, STOPPED might trigger 'Failure' wires or just end the graph.
            # For now, we treat STOPPED as a terminal state that halts flow.
            finished_heads = heads.filter(
                status_id__in=[HydraHeadStatus.SUCCESS, HydraHeadStatus.FAILED]
            )

            parents_with_children = HydraHead.objects.filter(
                spawn=self.spawn, provenance__isnull=False
            ).values_list('provenance_id', flat=True)

            for head in finished_heads:
                if head.id in parents_with_children:
                    continue

                self._process_graph_triggers(head)

            self._finalize_spawn_unsafe()

    def _dispatch_graph_roots(self) -> None:
        """Execute all Begin Play nodes."""
        all_nodes = self.spawn.spellbook.nodes.all()
        root_nodes = all_nodes.filter(is_root=True)

        if not root_nodes.exists() and all_nodes.exists():
            logger.error(
                f'[HYDRA] No Begin Play node found '
                f'for {self.spawn.spellbook.name}!'
            )
            return

        for node in root_nodes:
            self._create_head_from_node(node, provenance=None)

    def _process_graph_triggers(self, finished_head: HydraHead) -> None:
        """Follows the wires from a finished head based on Status Logic."""
        if not finished_head.node:
            return

        valid_wire_types = []
        valid_wire_types.append(HydraWireType.TYPE_FLOW)

        if finished_head.status_id == HydraHeadStatus.SUCCESS:
            valid_wire_types.append(HydraWireType.TYPE_SUCCESS)
        elif finished_head.status_id == HydraHeadStatus.FAILED:
            valid_wire_types.append(HydraWireType.TYPE_FAILURE)

        wires = HydraSpellbookConnectionWire.objects.filter(
            spellbook=self.spawn.spellbook,
            source=finished_head.node,
            type_id__in=valid_wire_types,
        )

        if not wires.exists():
            return

        logger.info(
            f'[HYDRA] Triggering {wires.count()} '
            f'wires from Head {finished_head.id}'
        )

        for wire in wires:
            self._create_head_from_node(
                node=wire.target, provenance=finished_head
            )

    def _create_head_from_node(
        self, node: HydraSpellbookNode, provenance: Optional[HydraHead]
    ):
        seed_head = HydraHead.objects.create(
            spawn=self.spawn,
            node=node,
            spell=node.spell,
            provenance=provenance,
            target=None,
            status_id=HydraHeadStatus.CREATED,
        )

        if node.invoked_spellbook:
            from .engine.graph_walker import GraphWalker

            walker = GraphWalker(spawn_id=self.spawn.id)
            walker.process_node(seed_head)
            return

        if node.distribution_mode:
            mode = node.distribution_mode_id
        else:
            mode = node.spell.distribution_mode_id

        if mode == HydraDistributionModeID.ALL_ONLINE_AGENTS:
            self._dispatch_fleet_wave(seed_head)
        elif mode == HydraDistributionModeID.SPECIFIC_TARGETS:
            self._dispatch_pinned_wave(seed_head)
        elif mode == HydraDistributionModeID.ONE_AVAILABLE_AGENT:
            self._dispatch_first_responder(seed_head)
        else:
            self._prepare_and_dispatch(seed_head)

    def _dispatch_fleet_wave(self, seed_head: HydraHead) -> None:
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
        active = self.spawn.heads.filter(
            status_id__in=[
                HydraHeadStatus.CREATED,
                HydraHeadStatus.PENDING,
                HydraHeadStatus.RUNNING,
                HydraHeadStatus.DELEGATED,
                HydraHeadStatus.STOPPING,
            ]
        )
        if active.exists():
            return

        if self.spawn.status_id == HydraSpawnStatus.STOPPING:
            new_status = HydraSpawnStatus.STOPPED
        else:
            new_status = HydraSpawnStatus.SUCCESS

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

    def _calculate_progress(self) -> float:
        return 0.0
