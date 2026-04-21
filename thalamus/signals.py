import logging

from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from django.dispatch import receiver

from central_nervous_system.models import Spike, SpikeTrain
from central_nervous_system.signals import spawn_failed, spawn_success
from frontal_lobe.models import ReasoningSession, ReasoningTurn
from hypothalamus.models import AIModelProviderUsageRecord
from identity.models import Identity, IdentityDisc
from parietal_lobe.models import ToolCall
from peripheral_nervous_system.models import NerveTerminalRegistry
from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask
from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Acetylcholine, Cortisol, Dopamine
from temporal_lobe.models import (
    Iteration,
    IterationShift,
    IterationShiftParticipant,
)

logger = logging.getLogger(__name__)


# ==========================================
# 1. STATUS BROADCASTERS (Dopamine / Cortisol)
# ==========================================


@receiver(post_save, sender=ReasoningTurn)
@receiver(post_save, sender=ReasoningSession)
@receiver(post_save, sender=Spike)
@receiver(post_save, sender=SpikeTrain)
def broadcast_status(sender, instance, **kwargs):
    if not hasattr(instance, 'status_id'):
        return

    # Safely extract the string name of the status, fallback to the ID string if the relation isn't prefetched
    try:
        status_name = instance.status.name.upper()
    except AttributeError:
        status_name = str(instance.status_id)

    # Determine the biological response based on the state
    # (Adjust these trigger words based on your exact DB status names)
    negative_states = ['ERROR', 'FAILED', 'STOPPING', 'MAXED_OUT']

    if status_name in negative_states:
        transmitter = Cortisol(
            receptor_class=sender.__name__,
            dendrite_id=str(instance.id),
            new_status=status_name,
        )
    else:
        transmitter = Dopamine(
            receptor_class=sender.__name__,
            dendrite_id=str(instance.id),
            new_status=status_name,
        )

    async_to_sync(fire_neurotransmitter)(transmitter)


# ==========================================
# 2. CHAT & TOOL UPDATES (Acetylcholine)
# ==========================================


@receiver(post_save, sender=ToolCall)
def broadcast_tool_call(sender, instance, **kwargs):
    msg_data = {
        'id': str(instance.id),
        'tool_name': instance.tool.name
        if hasattr(instance, 'tool')
        else 'Unknown',
        'arguments': instance.arguments,
        'result_payload': instance.result_payload,
        'traceback': instance.traceback,
    }

    transmitter = Acetylcholine(
        receptor_class=sender.__name__,
        dendrite_id=str(instance.id),
        activity='updated',
        vesicle=msg_data,
    )
    async_to_sync(fire_neurotransmitter)(transmitter)


# ==========================================
# 3. GLOBAL ENTITY SYNCS (Acetylcholine - Collections)
# ==========================================


@receiver(post_save, sender=AIModelProviderUsageRecord)
@receiver(post_save, sender=Identity)
@receiver(post_save, sender=IdentityDisc)
@receiver(post_save, sender=Iteration)
@receiver(post_save, sender=IterationShift)
@receiver(post_save, sender=IterationShiftParticipant)
@receiver(post_save, sender=NerveTerminalRegistry)
@receiver(post_save, sender=PFCEpic)
@receiver(post_save, sender=PFCStory)
@receiver(post_save, sender=PFCTask)
@receiver(post_save, sender=ReasoningSession)
@receiver(post_save, sender=ReasoningTurn)
def broadcast_global_entity(sender, instance, **kwargs):
    """
    Tells the frontend an entity was saved.
    Because dendrite_id is explicitly set, the frontend can update that exact row.
    """
    transmitter = Acetylcholine(
        receptor_class=sender.__name__,
        dendrite_id=str(instance.id),
        activity='saved',
    )
    async_to_sync(fire_neurotransmitter)(transmitter)


# ==========================================
# 4. CELERY / SYSTEM SIGNALS
# ==========================================


@receiver(spawn_failed)
def on_spawn_failed(sender, spike_train, **kwargs):
    logger.error(f'Spawn failed signal caught for SpikeTrain: {spike_train.id}')
    transmitter = Cortisol(
        receptor_class='SpikeTrain',
        dendrite_id=str(spike_train.id),
        new_status='SPAWN_FAILED',
    )
    async_to_sync(fire_neurotransmitter)(transmitter)


@receiver(spawn_success)
def on_spawn_success(sender, spike_train, **kwargs):
    logger.info(f'Spawn success signal caught for SpikeTrain: {spike_train.id}')
    transmitter = Dopamine(
        receptor_class='SpikeTrain',
        dendrite_id=str(spike_train.id),
        new_status='SPAWN_SUCCESS',
    )
    async_to_sync(fire_neurotransmitter)(transmitter)
