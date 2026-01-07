
from hydra.models import HydraSpellbook
from hydra.models import HydraSpawn
from django.utils import timezone


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
            self.spawn = HydraSpawn.objects.create(
                spellbook=book,
                environment_id=env_id
            )
        else:
            raise ValueError("Must provide either spawn_id or (spellbook_id + env_id)")

    def start(self):
        """
        Reads the Spellbook, creates the Heads (db objects), 
        and dispatches the first batch (order 0).
        """
        self.spawn.status = 1
        self.spawn.save()

        # 1. Materialize the Heads from the Spells
        spells = self.spawn.spellbook.spells.all().order_by('order')
        for spell in spells:
            HydraHead.objects.create(
                spawn=self.spawn,
                spell=spell
            )
        
        # 2. Trigger the first wave
        self._dispatch_next_wave()
        
    def _dispatch_next_wave(self):
        """
        Internal: Finds heads that are pending and have dependencies met.
        """
        # Logic to find the next 'order' group that hasn't run
        # For simple 'order' based grouping:
        # Get lowest order that is NOT complete and NOT running.
        pass

    def poll(self):
        """
        Updates state of all running heads from Celery.
        """
        active_heads = self.spawn.heads.exclude(celery_task_id__isnull=True)
        # Check AsyncResult for each...
        pass

    def heartbeat(self):
        """
        Called by a periodic task? 
        Checks health, ensures no zombies, updates the 'last_seen' on the Spawn.
        """
        self.spawn.last_heartbeat = timezone.now()
        self.spawn.save()
        # If headers are stuck, kill them or alert.

    def terminate(self):
        """
        Cuts off all heads.
        """
        running_heads = self.spawn.heads.filter(result_code__isnull=True)
        for head in running_heads:
            # revoke celery task
            # update DB status to 'Severed'
            pass
        self.spawn.status = 'terminated'
        self.spawn.save()

    def view(self):
        """
        Returns a dictionary summary for the frontend/API.
        """
        return {
            "id": self.spawn.id,
            "status": self.spawn.status,
            "heads": [
                {
                    "name": h.spell.executable.name,
                    "status": h.result_code,
                    "log_preview": h.spell_log[:100]
                }
                for h in self.spawn.heads.all()
            ]
        }