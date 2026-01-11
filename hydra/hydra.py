import json
import logging

from celery.result import AsyncResult
from django.db import transaction  # <--- IMPORT ADDED
from django.db.models import Min

from config.celery import app as celery_app
from .models import HydraSpellbook, HydraSpawn, HydraHead, HydraHeadStatus, HydraSpawnStatus
from .tasks import cast_hydra_spell

logger = logging.getLogger(__name__)


class Hydra(object):
    """
    Process Controller.
    Instantiated with a Spellbook ID (to start new) or Spawn ID (to monitor).
    """

    def __init__(self, spellbook_id=None, spawn_id=None, env_id=None):
        if spawn_id:
            # Re-attach to existing beast
            self.spawn = HydraSpawn.objects.get(id=spawn_id)
        elif spellbook_id and env_id:
            # Prepare a new beast
            book = HydraSpellbook.objects.get(id=spellbook_id)
            # Find or default the status
            self.spawn = HydraSpawn.objects.create(
                spellbook=book,
                environment_id=env_id,
                status_id=HydraSpawnStatus.CREATED)

            # Initialize empty context (JSON serialized to Text)
            self.spawn.context_data = json.dumps({})
            self.spawn.save()
        else:
            raise ValueError(
                "Must provide either spawn_id or (spellbook_id + env_id)")

    def start(self):
        """
        Reads the Spellbook, creates the Heads (db objects), 
        and dispatches the first batch.
        """
        # Update Status to Running
        self.spawn.status_id = HydraSpawnStatus.RUNNING
        self.spawn.save()

        # 1. Materialize the Heads from the Spells
        if not self.spawn.heads.exists():
            spells = self.spawn.spellbook.spells.all()

            for spell in spells:
                HydraHead.objects.create(spawn=self.spawn,
                                         spell=spell,
                                         status_id=HydraHeadStatus.CREATED)

        # 2. Trigger the first wave
        self._dispatch_next_wave()

    def _dispatch_next_wave(self):
        """
        Smart Dispatch: Finds the lowest 'order' that has PENDING/CREATED items
        and runs them. If lower orders are still RUNNING, it waits.
        """
        # 1. Are there any active/running heads?
        active_heads = self.spawn.heads.filter(
            status_id__in=[HydraHeadStatus.RUNNING, HydraHeadStatus.PENDING])

        if active_heads.exists():
            return

        # 2. Find the next batch of Created tasks
        pending_heads = self.spawn.heads.filter(
            status_id=HydraHeadStatus.CREATED)

        if not pending_heads.exists():
            self._finalize_spawn()
            return

        next_order = pending_heads.aggregate(
            Min('spell__order'))['spell__order__min']

        # 3. Dispatch that batch
        wave = pending_heads.filter(spell__order=next_order)

        for head in wave:
            logger.info(
                f"[HYDRA] Dispatching Head {head.id} (Order: {next_order}, Spell: {head.spell.name})"
            )

            # Update status to PENDING immediately to prevent double-dispatch
            head.status_id = HydraHeadStatus.PENDING
            head.save()

            # Use a default argument to capture the current head.id in the lambda
            transaction.on_commit(
                lambda h_id=head.id: cast_hydra_spell.delay(h_id))

    def poll(self):
        """
        Updates state of all running heads from Celery.
        """
        active_heads = self.spawn.heads.filter(
            status_id=HydraHeadStatus.RUNNING)
        state_changed = False

        for head in active_heads:
            if not head.celery_task_id:
                continue

            res = AsyncResult(head.celery_task_id)
            if res.ready():
                if res.state == 'FAILURE':
                    head.status_id = HydraHeadStatus.FAILED
                    head.execution_log += f"\n[HYDRA POLL] Task Failure detected: {res.info}"
                    head.save()
                    state_changed = True
                elif res.state == 'SUCCESS':
                    # If it's SUCCESS in Celery but still RUNNING in DB,
                    # it means the task finished but failed to update DB (unlikely but possible)
                    # OR we are polling while it's in a transition.
                    # We should probably let cast_hydra_spell handle it,
                    # but polling is a safety net.
                    pass

        self._dispatch_next_wave()

    def heartbeat(self):
        self.spawn.save()

    def _finalize_spawn(self):
        """
        Final check to see if the entire spawn is done.
        """
        # Are there any heads still in a non-terminal state?
        active_heads = self.spawn.heads.exclude(
            status_id__in=[HydraHeadStatus.SUCCESS, HydraHeadStatus.FAILED])

        if active_heads.exists():
            return

        failed_heads = self.spawn.heads.filter(status_id=HydraHeadStatus.FAILED)
        if failed_heads.exists():
            status_id = HydraSpawnStatus.FAILED
            status_name = "Failed"
        else:
            status_id = HydraSpawnStatus.SUCCESS
            status_name = "Success"

        self.spawn.status_id = status_id
        self.spawn.save()
        logger.info(f"[HYDRA] Spawn {self.spawn.id} Finalized: {status_name}")

        from .signals import spawn_failed, spawn_success
        if status_id == HydraSpawnStatus.FAILED:
            spawn_failed.send(sender=self.spawn.__class__, spawn=self.spawn)
        elif status_id == HydraSpawnStatus.SUCCESS:
            spawn_success.send(sender=self.spawn.__class__, spawn=self.spawn)

    def terminate(self):
        # 1. Kill Running Tasks
        running_heads = self.spawn.heads.filter(
            status_id__in=[HydraHeadStatus.RUNNING, HydraHeadStatus.PENDING])
        for head in running_heads:
            if head.celery_task_id:
                logger.info(f"[HYDRA] Revoking task {head.celery_task_id}")
                celery_app.control.revoke(head.celery_task_id, terminate=True)

            head.status_id = HydraHeadStatus.FAILED
            head.execution_log += "\n[HYDRA] Terminated by User."
            head.save()

        # 2. Update Spawn Status
        self.spawn.status_id = HydraSpawnStatus.FAILED
        self.spawn.save()

    def view(self):
        return {
            "id":
                str(self.spawn.id),
            "status":
                self.spawn.status.name,
            "heads": [{
                "name": h.spell.executable.name,
                "order": h.spell.order,
                "status_id": h.status.id,
                "status_name": h.status.name,
                "log_preview": (h.spell_log or "")[:100]
            } for h in self.spawn.heads.all().order_by('spell__order')]
        }
