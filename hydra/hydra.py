import json
import logging
from typing import Any, Dict, List, Optional

from celery.result import AsyncResult
from django.db import transaction
from django.db.models import Min

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
    Acts as the Synchronous Orchestrator. It interfaces with the Django ORM
    to manage state and dispatches tasks to the Async Workers (Celery/Talos).

    Key Pattern: 'Database Locking'
    Uses atomic transactions and row locking to ensure that parallel polling
    never results in double-dispatching of waves.
    """

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
        """Ignites the spawn."""
        self.spawn.status_id = HydraSpawnStatus.RUNNING
        self.spawn.save(update_fields=['status'])

        # Ensure heads exist (idempotent check)
        if not self.spawn.heads.exists():
            self._create_heads()

        self._dispatch_next_wave()

    def terminate(self) -> None:
        """
        Aborts the spawn.
        Revokes Celery tasks, trusting the 'Strict Leash' in the Agent
        to kill the actual subprocesses when the connection dies.
        """
        with transaction.atomic():
            # Lock the spawn to prevent status race conditions
            spawn = HydraSpawn.objects.select_for_update().get(id=self.spawn.id)

            running_heads = spawn.heads.select_for_update().filter(
                status_id__in=[HydraHeadStatus.RUNNING, HydraHeadStatus.PENDING]
            )

            for head in running_heads:
                if head.celery_task_id:
                    # terminate=True sends SIGTERM -> SIGKILL to the Celery Worker
                    celery_app.control.revoke(
                        head.celery_task_id, terminate=True
                    )

                head.status_id = HydraHeadStatus.ABORTED
                head.execution_log += (
                    '\n[HYDRA] Terminated by User (Signal Sent).\n'
                )
                head.save(update_fields=['status', 'execution_log'])

            spawn.status_id = HydraSpawnStatus.FAILED
            spawn.save(update_fields=['status'])

            logger.info(f'[HYDRA] Spawn {spawn.id} Terminated.')

    def poll(self) -> None:
        """
        Maintenance Pulse.
        Checks for crashed workers and dispatches the next wave if ready.
        """
        # 1. Check for 'Ghost' tasks (Celery failed but didn't write to DB)
        # We don't lock here to avoid blocking reads, as we are only reading status.
        active_heads = self.spawn.heads.filter(
            status_id=HydraHeadStatus.RUNNING
        )

        for head in active_heads:
            if not head.celery_task_id:
                continue

            res = AsyncResult(head.celery_task_id)
            # If Celery says it failed, but our DB thinks it's running, we have a Ghost.
            if res.ready() and res.state in ['FAILURE', 'REVOKED']:
                logger.warning(f'[HYDRA] Detected Ghost Task {head.id}')
                head.status_id = HydraHeadStatus.FAILED
                head.execution_log += (
                    f'\n[HYDRA POLL] Task Crash Detected: {res.info}\n'
                )
                head.save(update_fields=['status', 'execution_log'])

        # 2. Try to move forward
        self._dispatch_next_wave()

    def view(self) -> Dict[str, Any]:
        """Serializer for UI."""
        return {
            'id': str(self.spawn.id),
            'status': self.spawn.status.name,
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
        self.spawn = spawn  # update reference
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
        Uses Atomic Transactions to prevent race conditions during polling.
        """
        with transaction.atomic():
            # 1. Lock the Spawn rows for this transaction
            # This ensures no other 'poll' can modify these heads while we decide.
            heads = self.spawn.heads.select_for_update().all()

            # 2. Analyze State
            active_min_order = heads.filter(
                status_id__in=[HydraHeadStatus.RUNNING, HydraHeadStatus.PENDING]
            ).aggregate(Min('spell__order'))['spell__order__min']

            pending_min_order = heads.filter(
                status_id=HydraHeadStatus.CREATED
            ).aggregate(Min('spell__order'))['spell__order__min']

            # 3. Completion Check
            if pending_min_order is None:
                self._finalize_spawn_unsafe()
                return

            # 4. Blocking Rule
            # If Order 1 is running, we cannot start Order 2.
            if (
                active_min_order is not None
                and pending_min_order > active_min_order
            ):
                return

            # 5. Dispatch
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
                # on_commit ensures we don't dispatch to Celery until the DB lock is released
                transaction.on_commit(
                    lambda h_id=head.id: cast_hydra_spell.delay(h_id)
                )

    def _finalize_spawn_unsafe(self) -> None:
        """
        Determines final status.
        'Unsafe' suffix implies it must be called within an atomic block (which it is).
        """
        # Are there any stragglers?
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

        # Only save if status changed to avoid signal spam
        if self.spawn.status_id != new_status:
            self.spawn.status_id = new_status
            self.spawn.save(update_fields=['status'])
            self._trigger_completion_signals(new_status)

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
