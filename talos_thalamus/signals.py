from django.dispatch import receiver
from hydra.signals import spawn_failed, spawn_success
from .models import Stimulus
from talos_frontal.logic import process_stimulus


@receiver(spawn_failed)
def on_spawn_failed(sender, spawn, **kwargs):
    stimulus = Stimulus(source='hydra',
                        description=f"Spawn {spawn.id} Failed",
                        context_data={
                            'spawn_id': spawn.id,
                            'event_type': 'spawn_failed'
                        })
    process_stimulus(stimulus)


@receiver(spawn_success)
def on_spawn_success(sender, spawn, **kwargs):
    stimulus = Stimulus(source='hydra',
                        description=f"Spawn {spawn.id} Succeeded",
                        context_data={
                            'spawn_id': spawn.id,
                            'event_type': 'spawn_success'
                        })
    process_stimulus(stimulus)
