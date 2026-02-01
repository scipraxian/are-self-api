from django.dispatch import Signal
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import HydraSpawn, HydraStatusID
# Delayed import of GraphWalker to avoid circularity if any,
# though signals.py is usually safe.

spawn_failed = Signal()
spawn_success = Signal()


@receiver(post_save, sender=HydraSpawn)
def on_spawn_update(sender, instance, created, **kwargs):
    """
    Reactive Event Loop:
    1. Checks if the Spawn has finished (Success/Fail).
    2. Checks if it is a Child (has parent_head).
    3. Wakes up the Parent Node to continue the Master Graph.
    """
    if created:
        return

    # Only react to terminal states
    if instance.status_id not in [HydraStatusID.SUCCESS, HydraStatusID.FAILED]:
        return

    # Check for Parent Link (Delegation)
    if instance.parent_head:
        from .engine.graph_walker import GraphWalker

        parent_head = instance.parent_head

        # Map Child Status -> Parent Status
        # If Child Failed, Parent Fails. If Child Success, Parent Success.
        parent_head.status_id = instance.status_id
        parent_head.save(update_fields=['status'])

        # LOGGING (Crucial for debugging recursion)
        print(
            f"[SIGNAL] Child Spawn {instance.id} woke up Parent Node {parent_head.id}. Resuming Parent Graph."
        )

        # RESUME PARENT GRAPH
        # We instantiate the walker on the PARENT's Spawn (the spawn that owns the parent node)
        walker = GraphWalker(spawn_id=parent_head.spawn.id)
        walker.process_node(parent_head)
