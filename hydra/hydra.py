import json
import logging
import subprocess

from celery.result import AsyncResult
from django.db import transaction
from django.db.models import Min

from config.celery import app as celery_app
from .models import HydraHead, HydraHeadStatus, HydraSpawn, HydraSpawnStatus, HydraSpellbook
from .tasks import cast_hydra_spell

logger = logging.getLogger(__name__)


class Hydra(object):
    def __init__(self, spellbook_id=None, spawn_id=None, env_id=None):
        if spawn_id:
            self.spawn = HydraSpawn.objects.get(id=spawn_id)
        elif spellbook_id and env_id:
            book = HydraSpellbook.objects.get(id=spellbook_id)
            self.spawn = HydraSpawn.objects.create(
                spellbook=book,
                environment_id=env_id,
                status_id=HydraSpawnStatus.CREATED)
            self.spawn.context_data = json.dumps({})
            self.spawn.save()
        else:
            raise ValueError("Must provide either spawn_id or (spellbook_id + env_id)")

    def start(self):
        self.spawn.status_id = HydraSpawnStatus.RUNNING
        self.spawn.save()
        if not self.spawn.heads.exists():
            spells = self.spawn.spellbook.spells.all()
            for spell in spells:
                HydraHead.objects.create(spawn=self.spawn, spell=spell, status_id=HydraHeadStatus.CREATED)
        self._dispatch_next_wave()

    def _dispatch_next_wave(self):
        """
        PARALLEL DISPATCH:
        Allows multiple heads to run simultaneously IF they share the same Order ID.
        """
        # 1. What is currently running?
        active_min_order = self.spawn.heads.filter(
            status_id__in=[HydraHeadStatus.RUNNING, HydraHeadStatus.PENDING]
        ).aggregate(Min('spell__order'))['spell__order__min']

        # 2. What is waiting to run?
        pending_min_order = self.spawn.heads.filter(
            status_id=HydraHeadStatus.CREATED
        ).aggregate(Min('spell__order'))['spell__order__min']

        if pending_min_order is None:
            self._finalize_spawn()
            return

        # 3. BLOCKING RULE:
        # If running tasks exist in Order 1, and next tasks are Order 2, WAIT.
        if active_min_order is not None and pending_min_order > active_min_order:
            return

        # 4. DISPATCH RULE:
        # If (Nothing Running) OR (Running Order == Pending Order), DISPATCH ALL.
        wave = self.spawn.heads.filter(
            status_id=HydraHeadStatus.CREATED,
            spell__order=pending_min_order
        )

        for head in wave:
            logger.info(f"[HYDRA] Parallel Dispatch Head {head.id} (Order: {pending_min_order})")
            head.status_id = HydraHeadStatus.PENDING
            head.save()
            transaction.on_commit(lambda h_id=head.id: cast_hydra_spell.delay(h_id))

    def poll(self):
        active_heads = self.spawn.heads.filter(status_id=HydraHeadStatus.RUNNING)
        for head in active_heads:
            if not head.celery_task_id: continue
            res = AsyncResult(head.celery_task_id)
            if res.ready() and res.state == 'FAILURE':
                head.status_id = HydraHeadStatus.FAILED
                head.execution_log += f"\n[HYDRA POLL] Task Failure detected: {res.info}"
                head.save()

        self._dispatch_next_wave()

    def heartbeat(self):
        self.spawn.save()

    def _finalize_spawn(self):
        active_heads = self.spawn.heads.exclude(status_id__in=[HydraHeadStatus.SUCCESS, HydraHeadStatus.FAILED])
        if active_heads.exists(): return

        failed_heads = self.spawn.heads.filter(status_id=HydraHeadStatus.FAILED)
        status_id = HydraSpawnStatus.FAILED if failed_heads.exists() else HydraSpawnStatus.SUCCESS
        self.spawn.status_id = status_id
        self.spawn.save()
        logger.info(f"[HYDRA] Spawn {self.spawn.id} Finalized")

        from .signals import spawn_failed, spawn_success
        if status_id == HydraSpawnStatus.FAILED:
            spawn_failed.send(sender=self.spawn.__class__, spawn=self.spawn)
        elif status_id == HydraSpawnStatus.SUCCESS:
            spawn_success.send(sender=self.spawn.__class__, spawn=self.spawn)

    def terminate(self):
        # Revoke Celery
        running_heads = self.spawn.heads.filter(status_id__in=[HydraHeadStatus.RUNNING, HydraHeadStatus.PENDING])
        for head in running_heads:
            if head.celery_task_id:
                celery_app.control.revoke(head.celery_task_id, terminate=True)
            head.status_id = HydraHeadStatus.FAILED
            head.execution_log += "\n[HYDRA] Terminated by User."
            head.save()

        # Physical Kill
        try:
            env = self.spawn.environment.project_environment
            project_name = env.project_name if env else "HSHVacancy"

            # Local
            subprocess.run(f"taskkill /F /IM {project_name}.exe", shell=True, stderr=subprocess.DEVNULL)

            # Remote
            from core.models import RemoteTarget
            from talos_agent.utils.client import TalosAgentClient
            for target in RemoteTarget.objects.filter(status='ONLINE'):
                try:
                    TalosAgentClient(target.ip_address, port=target.agent_port, timeout=1.0).kill(project_name)
                except:
                    pass
        except:
            pass

        self.spawn.status_id = HydraSpawnStatus.FAILED
        self.spawn.save()

    def view(self):
        return {
            "id": str(self.spawn.id),
            "status": self.spawn.status.name,
            "heads": [{
                "name": h.spell.executable.name,
                "order": h.spell.order,
                "status_id": h.status.id,
                "status_name": h.status.name,
                "log_preview": (h.spell_log or "")[:100]
            } for h in self.spawn.heads.all().order_by('spell__order')]
        }
