from django.dispatch import receiver
from hydra.signals import spawn_failed, spawn_success
from .models import Stimulus
from .types import SignalTypeID
from talos_frontal.logic import process_stimulus


@receiver(spawn_failed)
def on_spawn_failed(sender, spawn, **kwargs):
    # Find the representative head that failed
    failed_head = spawn.heads.filter(status_id=5).last()  # FAILED=5
    head_id = str(failed_head.id) if failed_head else None

    stimulus = Stimulus(source='hydra',
                        description=f"Spawn {spawn.id} Failed",
                        context_data={
                            'spawn_id': str(spawn.id),
                            'head_id': head_id,
                            'event_type': SignalTypeID.SPAWN_FAILED
                        })
    process_stimulus(stimulus)


@receiver(spawn_success)
def on_spawn_success(sender, spawn, **kwargs):
    # For success, link to the last head in sequence
    last_head = spawn.heads.order_by('spell__order').last()
    head_id = str(last_head.id) if last_head else None

    stimulus = Stimulus(source='hydra',
                        description=f"Spawn {spawn.id} Succeeded",
                        context_data={
                            'spawn_id': str(spawn.id),
                            'head_id': head_id,
                            'event_type': SignalTypeID.SPAWN_SUCCESS
                        })
    process_stimulus(stimulus)
