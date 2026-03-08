from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from .models import CNSStatusID, SpikeTrain
from .tasks import check_next_wave  # Import the celery task directly

spawn_failed = Signal()
spawn_success = Signal()


@receiver(post_save, sender=SpikeTrain)
def on_spawn_update(sender, instance, created, **kwargs):
    """
    Reactive Event Loop:
    1. Checks if the SpikeTrain has finished (Success/Fail).
    2. Checks if it is a Child (has parent_spike).
    3. Wakes up the Parent Node to continue the Master Graph.
    """
    if created:
        return

    # Only react to terminal states
    if instance.status_id not in [CNSStatusID.SUCCESS, CNSStatusID.FAILED]:
        return

    # Check for Parent Link (Delegation)
    if instance.parent_spike:
        parent_spike = instance.parent_spike

        # Map Child Status -> Parent Status
        # If Child Failed, Parent Fails. If Child Success, Parent Success.
        parent_spike.status_id = instance.status_id
        parent_spike.save(update_fields=['status'])

        # LOGGING (Crucial for debugging recursion)
        print(
            f'[SIGNAL] Child SpikeTrain {instance.id} finished. '
            f'Woke up Parent Node {parent_spike.id}. Resuming Parent Graph.'
        )

        # RESUME PARENT GRAPH
        # By calling the celery task, the parent CNS will boot up, see the
        # newly finished spike, and naturally traverse its outgoing wires.
        # This completely replaces the GraphWalker hack.
        transaction.on_commit(
            lambda: check_next_wave.delay(parent_spike.spike_train.id)
        )
