import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from celery.result import AsyncResult
from django.db import transaction
from django.db.models import Min
from django.utils import timezone

from config.celery import app as celery_app

from .models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpellbook,
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
        spawn_id: Optional[int] = None,
        env_id: Optional[int] = None,
    ):
        if spawn_id:
            self.spawn = HydraSpawn.objects.get(id=spawn_id)
        elif spellbook_id and env_id:
            self.spawn = self._create_spawn(spellbook_id, env_id)
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
        self._dispatch_next_wave()

    def terminate(self) -> None:
        """
        Aborts the spawn.

        CRITICAL: Performs DB updates inside the lock, but pushes
        Celery revocation (Network I/O) outside to prevent DB deadlocks.
        """
        task_ids_to_revoke = []

        with transaction.atomic():
            spawn = HydraSpawn.objects.select_for_update().get(id=self.spawn.id)

            # Don't terminate if already done
            if spawn.status_id in [
                HydraSpawnStatus.SUCCESS,
                HydraSpawnStatus.FAILED,
            ]:
                logger.info(
                    f'[HYDRA] Spawn {spawn.id} already finalized, ignoring terminate.'
                )
                return

            # Lock running heads
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
                    task_ids_to_revoke.append(head.celery_task_id)

                head.status_id = HydraHeadStatus.ABORTED
                head.execution_log += (
                    '\n[HYDRA] Terminated by User (Signal Sent).\n'
                )
                head.save(update_fields=['status', 'execution_log'])

            spawn.status_id = HydraSpawnStatus.FAILED
            spawn.save(update_fields=['status'])

        # --- Network Operations (Outside Lock) ---
        for task_id in task_ids_to_revoke:
            try:
                celery_app.control.revoke(str(task_id), terminate=True)
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
        self._dispatch_next_wave()

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

    def _create_spawn(self, spellbook_id: int, env_id: int) -> HydraSpawn:
        book = HydraSpellbook.objects.get(id=spellbook_id)
        spawn = HydraSpawn.objects.create(
            spellbook=book,
            environment_id=env_id,
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

    def _dispatch_next_wave(self) -> None:
        """
        Parallel Dispatch Engine.
        Uses Atomic Transactions to prevent race conditions.
        """
        with transaction.atomic():
            heads = self.spawn.heads.select_for_update().all()

            # Analyze State
            active_min_order = heads.filter(
                status_id__in=[HydraHeadStatus.RUNNING, HydraHeadStatus.PENDING]
            ).aggregate(Min('spell__order'))['spell__order__min']

            pending_min_order = heads.filter(
                status_id=HydraHeadStatus.CREATED
            ).aggregate(Min('spell__order'))['spell__order__min']

            # Completion Check
            if pending_min_order is None:
                self._finalize_spawn_unsafe()
                return

            # Blocking Rule
            if (
                active_min_order is not None
                and pending_min_order > active_min_order
            ):
                return

            # Dispatch Wave
            wave = heads.filter(
                status_id=HydraHeadStatus.CREATED,
                spell__order=pending_min_order,
            )

            if not wave.exists():
                return

            logger.info(
                f'[HYDRA] Dispatching Wave {pending_min_order} ({wave.count()} heads)'
            )

            for head in wave:
                head.status_id = HydraHeadStatus.PENDING
                head.save(update_fields=['status'])

                # Closure to capture ID by value and save Task ID on dispatch
                def dispatch_and_record(h_id: int):
                    result = cast_hydra_spell.delay(h_id)
                    # We must run this update in a separate quick query to ensure visibility
                    HydraHead.objects.filter(id=h_id).update(
                        celery_task_id=result.id
                    )

                # on_commit ensures we don't dispatch until the DB lock is released
                transaction.on_commit(
                    lambda h_id=head.id: dispatch_and_record(h_id)
                )

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
