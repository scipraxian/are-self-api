import logging

from django.dispatch import receiver

from hydra.signals import spawn_failed, spawn_success

logger = logging.getLogger(__name__)


@receiver(spawn_failed)
def on_spawn_failed(sender, spawn, **kwargs):
    pass


@receiver(spawn_success)
def on_spawn_success(sender, spawn, **kwargs):
    pass