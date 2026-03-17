from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import CNSStatusID, Spike, SpikeTrain
from .tasks import check_next_wave  # Import the celery task directly

spawn_failed = Signal()
spawn_success = Signal()
spike_status_changed = Signal()


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


@receiver(post_save, sender=Spike)
def on_spike_status_changed(sender, instance: Spike, **kwargs):
    """
    Emits websocket lifecycle events when a Spike's status changes.
    """
    if not instance or instance.id is None:
        return

    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    # Broadcast over the spike_log_<uuid> group so listeners can sync lifecycle.
    group_name = f'spike_log_{instance.id}'
    payload = {
        'type': 'spike.status',
        'spike_id': str(instance.id),
        'status_id': instance.status_id,
    }

    # Fire both the Django signal (for in-process listeners) and the socket event.
    spike_status_changed.send(
        sender=sender,
        spike=instance,
        status_id=instance.status_id,
    )

    try:
        async_to_sync(channel_layer.group_send)(group_name, payload)
    except Exception:
        # Socket failures should never break DB writes.
        pass
