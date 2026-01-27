import json
import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

from celery.result import AsyncResult
from django.db import transaction
from django.db.models import Min
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
    HydraStatusID,
)
from .tasks import cast_hydra_spell

logger = logging.getLogger(__name__)


class Hydra:
    """
    The High-Level Job Manager.

    Architecture:
    -------------
    Acts as the Synchronous Orchestrator using 'Database Locking' to ensure
    safe parallel execution.

    Major Capabilities:
    1. Parallel Wave Dispatching (Atomic).
    2. Ghost Task Detection & Stale Task Recovery.
    3. Safe Termination (Network calls outside DB locks).
    """

    STALE_PENDING_TIMEOUT = timedelta(minutes=5)

    def __init__(
        self,
        spellbook_id: Optional[int] = None,
        spawn_id: Optional[uuid] = None,
    ):
        if spawn_id:
            self.spawn = HydraSpawn.objects.get(id=spawn_id)
        elif spellbook_id:
            self.spawn = self._create_spawn(spellbook_id)
        else:
            raise ValueError(
                'Must provide either spawn_id or (spellbook_id + env_id)'
            )

    def start(self) -> None:
        """Ignites the spawn idempotently."""
        with transaction.atomic():
            # Lock row to prevent double-start race conditions
            spawn = HydraSpawn.objects.select_for_update().get(id=self.spawn.id)

            if spawn.status_id != HydraSpawnStatus.CREATED:
                logger.warning(f'[HYDRA] Spawn {spawn.id} already started.')
                return

            spawn.status_id = HydraSpawnStatus.RUNNING
            spawn.save(update_fields=['status'])

            # Ensure heads exist
            if not spawn.heads.exists():
                self._create_heads()

        # Dispatch first wave (New Transaction)
        self.dispatch_next_wave()

    def terminate(self) -> None:
        """
        Aborts the spawn.
        """
        task_ids_to_revoke = []

        with transaction.atomic():
            spawn = HydraSpawn.objects.select_for_update().get(id=self.spawn.id)

            if spawn.status_id in [
                HydraSpawnStatus.SUCCESS,
                HydraSpawnStatus.FAILED,
            ]:
                logger.info(
                    f'[HYDRA] Spawn {spawn.id} already finalized, ignoring terminate.'
                )
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

        # --- Network Operations ---
        for task_id in task_ids_to_revoke:
            try:
                # Soft revoke only (stops it if it hasn't started yet)
                # We do NOT use terminate=True anymore because it fails on Windows
                # and we have a better Heartbeat system now.
                celery_app.control.revoke(task_id, terminate=False)
            except Exception as e:
                logger.warning(f'Failed to revoke task {task_id}: {e}')

        logger.info(f'[HYDRA] Spawn {self.spawn.id} Terminated.')

    def poll(self) -> None:
        """
        Maintenance Pulse.
        Checks for crashed workers, stale tasks, and dispatches the next wave.
        """
        with transaction.atomic():
            # 1. Ghost Detection: Tasks that Celery marked failed/revoked
            # We lock these rows to ensure no one else is updating them
            active_heads = self.spawn.heads.select_for_update().filter(
                status_id=HydraHeadStatus.RUNNING
            )

            for head in active_heads:
                if not head.celery_task_id:
                    continue

                res = AsyncResult(str(head.celery_task_id))
                if res.ready() and res.state in ['FAILURE', 'REVOKED']:
                    logger.warning(f'[HYDRA] Detected Ghost Task {head.id}')
                    head.status_id = HydraHeadStatus.FAILED
                    head.execution_log += (
                        f'\n[HYDRA POLL] Task Crash Detected: {res.info}\n'
                    )
                    head.save(update_fields=['status', 'execution_log'])

            # 2. Stale Pending Detection: Tasks dispatched but never picked up
            stale_threshold = timezone.now() - self.STALE_PENDING_TIMEOUT
            stale_heads = self.spawn.heads.select_for_update().filter(
                status_id=HydraHeadStatus.PENDING,
                modified__lt=stale_threshold,
            )

            for head in stale_heads:
                logger.warning(f'[HYDRA] Stale PENDING task {head.id}')
                head.status_id = HydraHeadStatus.FAILED
                head.execution_log += (
                    '\n[HYDRA POLL] Task never started (timeout).\n'
                )
                head.save(update_fields=['status', 'execution_log'])

        # 3. Try to move forward (New Transaction)
        self.dispatch_next_wave()

    def view(self) -> Dict[str, Any]:
        """Serializer for UI."""
        return {
            'id': str(self.spawn.id),
            'status': self.spawn.status.name,
            'progress': self._calculate_progress(),
            'current_wave': self._get_current_wave(),
            'heads': [
                {
                    'name': h.spell.executable.name,
                    'order': h.spell.order,
                    'status_id': h.status.id,
                    'status_name': h.status.name,
                    'log_preview': (h.spell_log or '')[:150],
                }
                for h in self.spawn.heads.all()
                .select_related('spell', 'status')
                .order_by('spell__order')
            ],
        }

    # =========================================================================
    # Internal Logic
    # =========================================================================

    def _create_spawn(self, spellbook_id: int) -> HydraSpawn:
        book = HydraSpellbook.objects.get(id=spellbook_id)
        spawn = HydraSpawn.objects.create(
            spellbook=book,
            status_id=HydraSpawnStatus.CREATED,
            context_data=json.dumps({}),
        )
        self.spawn = spawn
        self._create_heads()
        return spawn

    def _create_heads(self) -> None:
        heads = [
            HydraHead(
                spawn=self.spawn, spell=spell, status_id=HydraHeadStatus.CREATED
            )
            for spell in self.spawn.spellbook.spells.all()
        ]
        HydraHead.objects.bulk_create(heads)

    def dispatch_next_wave(self) -> None:
        """
        Parallel Dispatch Engine.
        Evaluates distribution modes to fan out tasks across the fleet.
        """
        with transaction.atomic():
            heads = self.spawn.heads.select_for_update().all()

            # Analyze State
            pending_min_order = heads.filter(
                status_id=HydraStatusID.CREATED
            ).aggregate(Min('spell__order'))['spell__order__min']

            if pending_min_order is None:
                self._finalize_spawn_unsafe()
                return

            # Blocking Rule: Don't start next wave if previous wave is still running
            active_min_order = heads.filter(
                status_id__in=[HydraStatusID.RUNNING, HydraStatusID.PENDING]
            ).aggregate(Min('spell__order'))['spell__order__min']

            if active_min_order is not None and pending_min_order > active_min_order:
                return

            wave = heads.filter(
                status_id=HydraStatusID.CREATED,
                spell__order=pending_min_order,
            )

            for head in wave:
                mode = head.spell.distribution_mode_id

                if mode == HydraDistributionModeID.ALL_ONLINE_AGENTS:
                    self._dispatch_fleet_wave(head)
                elif mode == HydraDistributionModeID.SPECIFIC_TARGETS:
                    self._dispatch_pinned_wave(head)
                else:
                    # LOCAL_SERVER or ONE_AVAILABLE logic
                    self._prepare_and_dispatch(head)

    def _dispatch_fleet_wave(self, seed_head: HydraHead) -> None:
        """Fans out a single spell to all online agents."""
        agents = TalosAgentRegistry.objects.filter(
            status_id=TalosAgentStatus.ONLINE)  # could be in use?

        if not agents.exists():
            logger.warning(
                f'[HYDRA] No online agents for fleet '
                f'spell: {seed_head.spell.name}')
            seed_head.status_id = HydraStatusID.FAILED
            seed_head.execution_log += ('\n[ERROR] No online agents available '
                                        'for fleet distribution.\n')
            seed_head.save(update_fields=['status', 'execution_log'])
            return

        for agent in agents:
            self._clone_and_dispatch_head(seed_head, agent)

        # Remove the 'Seed' head as it has been replaced by targeted clones
        seed_head.delete()

    def _dispatch_pinned_wave(self, seed_head: HydraHead) -> None:
        """Dispatches to explicitly pinned targets."""
        targets = seed_head.spell.specific_targets.all()
        for t in targets:
            self._clone_and_dispatch_head(seed_head, t.target)
        seed_head.delete()

    def _clone_and_dispatch_head(self, seed: HydraHead,
                                 agent: TalosAgentRegistry) -> None:
        """The Helper: Multiplies a head for a specific target and queues the task."""
        new_head = HydraHead.objects.create(
            spawn=seed.spawn,
            spell=seed.spell,
            target=agent,
            status_id=HydraStatusID.PENDING
        )

        def queue_task(h_id):
            res = cast_hydra_spell.delay(h_id)
            HydraHead.objects.filter(id=h_id).update(celery_task_id=res.id)

        transaction.on_commit(lambda: queue_task(new_head.id))

    def _prepare_and_dispatch(self, head: HydraHead) -> None:
        """Standard dispatch for single-target or local tasks."""
        head.status_id = HydraStatusID.PENDING
        head.save(update_fields=['status'])

        transaction.on_commit(lambda: cast_hydra_spell.delay(head.id))
    def _finalize_spawn_unsafe(self) -> None:
        """Determines final status inside a transaction."""
        active = self.spawn.heads.exclude(
            status_id__in=[
                HydraHeadStatus.SUCCESS,
                HydraHeadStatus.FAILED,
                HydraHeadStatus.ABORTED,
            ]
        )
        if active.exists():
            return

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

            # Defer signals until after commit to avoid holding locks
            transaction.on_commit(
                lambda: self._trigger_completion_signals(new_status)
            )

    def _trigger_completion_signals(self, status_id: int) -> None:
        logger.info(
            f'[HYDRA] Spawn {self.spawn.id} Finalized: {self.spawn.status.name}'
        )
        from .signals import spawn_failed, spawn_success

        sender = self.spawn.__class__
        if status_id == HydraSpawnStatus.FAILED:
            spawn_failed.send(sender=sender, spawn=self.spawn)
        elif status_id == HydraSpawnStatus.SUCCESS:
            spawn_success.send(sender=sender, spawn=self.spawn)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _calculate_progress(self) -> float:
        total = self.spawn.heads.count()
        if total == 0:
            return 0.0
        done = self.spawn.heads.filter(
            status_id__in=[
                HydraHeadStatus.SUCCESS,
                HydraHeadStatus.FAILED,
                HydraHeadStatus.ABORTED,
            ]
        ).count()
        return round((done / total) * 100, 1)

    def _get_current_wave(self) -> Optional[int]:
        return self.spawn.heads.filter(
            status_id__in=[HydraHeadStatus.RUNNING, HydraHeadStatus.PENDING]
        ).aggregate(Min('spell__order'))['spell__order__min']
