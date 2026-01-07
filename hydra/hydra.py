import json
import logging
from django.utils import timezone
from celery.result import AsyncResult
from config.celery import app as celery_app
from .models import HydraSpellbook, HydraSpawn, HydraHead, HydraHeadStatus, HydraSpawnStatus
from .tasks import cast_hydra_spell
from environments.models import ProjectEnvironment

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
            status_created, _ = HydraSpawnStatus.objects.get_or_create(
                id=HydraSpawnStatus.CREATED, 
                defaults={'name': 'Created'}
            )
            
            # Create Spawn
            self.spawn = HydraSpawn.objects.create(
                spellbook=book,
                environment_id=env_id,
                status=status_created
            )
            
            # Initialize empty context (JSON serialized to Text)
            self.spawn.context_data = json.dumps({}) 
            self.spawn.save()
        else:
            raise ValueError("Must provide either spawn_id or (spellbook_id + env_id)")

    def start(self):
        """
        Reads the Spellbook, creates the Heads (db objects), 
        and dispatches the first batch.
        """
        # Update Status to Running
        status_running, _ = HydraSpawnStatus.objects.get_or_create(
            id=HydraSpawnStatus.RUNNING, 
            defaults={'name': 'Running'}
        )
        self.spawn.status = status_running
        self.spawn.save()

        # 1. Materialize the Heads from the Spells
        spells = self.spawn.spellbook.spells.all()
        
        status_created, _ = HydraHeadStatus.objects.get_or_create(
            id=HydraHeadStatus.CREATED, 
            defaults={'name': 'Created'}
        )

        for spell in spells:
            HydraHead.objects.create(
                spawn=self.spawn,
                spell=spell,
                status=status_created
            )
        
        # 2. Trigger the first wave
        self._dispatch_next_wave()
        
    def _dispatch_next_wave(self):
        """
        Internal: Finds heads that are pending and dispatches them.
        For V1 "Fast Validate", we just run everything that isn't finished.
        """
        heads_to_run = self.spawn.heads.filter(status__id=HydraHeadStatus.CREATED)
        
        for head in heads_to_run:
            logger.info(f"[HYDRA] Dispatching Head {head.id} (Spell: {head.spell.name})")
            # Send to Celery
            cast_hydra_spell.delay(head.id)

    def poll(self):
        """
        Updates state of all running heads from Celery.
        Useful if the Celery task crashed without updating the DB.
        """
        active_heads = self.spawn.heads.filter(status__id=HydraHeadStatus.RUNNING)
        
        for head in active_heads:
            if not head.celery_task_id:
                continue
                
            res = AsyncResult(head.celery_task_id)
            if res.state == 'FAILURE':
                # Task crashed hard (exception)
                fail_status, _ = HydraHeadStatus.objects.get_or_create(
                    id=HydraHeadStatus.FAILED, 
                    defaults={'name': 'Failed'}
                )
                head.status = fail_status
                head.execution_log += f"\n[HYDRA POLL] Task Failure detected: {res.info}"
                head.save()

    def heartbeat(self):
        """
        Updates the 'modified' timestamp on the Spawn to show it's alive.
        """
        self.spawn.save()

    def terminate(self):
        """
        Cuts off all heads. Revokes Celery tasks and marks DB status.
        """
        # 1. Kill Running Tasks
        running_heads = self.spawn.heads.filter(status__id=HydraHeadStatus.RUNNING)
        for head in running_heads:
            if head.celery_task_id:
                logger.info(f"[HYDRA] Revoking task {head.celery_task_id}")
                celery_app.control.revoke(head.celery_task_id, terminate=True)
            
            # Update DB Status
            fail_status, _ = HydraHeadStatus.objects.get_or_create(
                id=HydraHeadStatus.FAILED, 
                defaults={'name': 'Failed'}
            )
            head.status = fail_status
            head.execution_log += "\n[HYDRA] Terminated by User."
            head.save()

        # 2. Update Spawn Status
        fail_spawn, _ = HydraSpawnStatus.objects.get_or_create(
            id=HydraSpawnStatus.FAILED, 
            defaults={'name': 'Failed'}
        )
        self.spawn.status = fail_spawn
        self.spawn.save()

    def view(self):
        """
        Returns a dictionary summary for the frontend/API.
        """
        return {
            "id": str(self.spawn.id),
            "status": self.spawn.status.name,
            "heads": [
                {
                    "name": h.spell.executable.name,
                    "status_id": h.status.id,
                    "status_name": h.status.name,
                    "log_preview": (h.spell_log or "")[:100]
                }
                for h in self.spawn.heads.all()
            ]
        }