import logging

from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from django.dispatch import receiver

from central_nervous_system.models import Spike, SpikeTrain
from central_nervous_system.signals import spawn_failed, spawn_success
from frontal_lobe.models import ChatMessage, ReasoningSession, ReasoningTurn
from identity.models import IdentityDisc
from parietal_lobe.models import ToolCall
from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask
from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Acetylcholine, Dopamine
from temporal_lobe.models import (
    Iteration,
    IterationShift,
    IterationShiftParticipant,
)

logger = logging.getLogger(__name__)


def get_spike_id(instance):
    """
    Helper to traverse relationships and find the target spike_id for the socket group.
    """
    if hasattr(instance, 'spike_id'):
        return instance.spike_id
    elif hasattr(instance, 'session') and hasattr(instance.session, 'spike_id'):
        return instance.session.spike_id
    elif hasattr(instance, 'turn') and hasattr(instance.turn, 'session'):
        return instance.turn.session.spike_id

    # If this is a global entity, we fall back to its own ID.
    # CRITICAL: Your React frontend MUST be listening to a synapse group matching this ID!
    return getattr(instance, 'id', None)


# ==========================================
# 1. FRONTAL LOBE SIGNALS
# ==========================================

@receiver(post_save, sender=ChatMessage)
def broadcast_chat_message(sender, instance, created, **kwargs):
    if not created:
        return

    spike_id = get_spike_id(instance)
    if not spike_id:
        return

    # Safely retrieve role name without forcing a DB lookup crash
    try:
        role_name = instance.role.name.lower()
    except AttributeError:
        role_name = str(instance.role_id)

    msg_data = {
        'id': str(instance.id),
        'role': role_name,
        'content': instance.content,
        'is_volatile': instance.is_volatile,
    }

    transmitter = Acetylcholine(
        spike_id=spike_id, key='chat_message', value=msg_data
    )
    async_to_sync(fire_neurotransmitter)(transmitter)


@receiver(post_save, sender=ReasoningTurn)
def broadcast_turn_status(sender, instance, **kwargs):
    spike_id = get_spike_id(instance)
    if not spike_id:
        return
    transmitter = Dopamine(spike_id=spike_id, status_id=instance.status_id)
    async_to_sync(fire_neurotransmitter)(transmitter)


@receiver(post_save, sender=ToolCall)
def broadcast_tool_call(sender, instance, **kwargs):
    spike_id = get_spike_id(instance)
    if not spike_id:
        return

    transmitter = Acetylcholine(
        spike_id=spike_id,
        key='tool_call_update',
        value={
            'id': str(instance.id),
            'tool_name': instance.tool.name if hasattr(instance, 'tool') else 'Unknown',
            'arguments': instance.arguments,
            'result_payload': instance.result_payload,
            'traceback': instance.traceback,
        },
    )
    async_to_sync(fire_neurotransmitter)(transmitter)


@receiver(post_save, sender=ReasoningSession)
def broadcast_session_status(sender, instance, **kwargs):
    spike_id = get_spike_id(instance)
    if not spike_id:
        return
    transmitter = Dopamine(spike_id=spike_id, status_id=instance.status_id)
    async_to_sync(fire_neurotransmitter)(transmitter)


# ==========================================
# 2. CNS SIGNALS
# ==========================================

@receiver(post_save, sender=Spike)
@receiver(post_save, sender=SpikeTrain)
def broadcast_cns_status(sender, instance, **kwargs):
    # Fix: SpikeTrain doesn't have a spike_id, so we broadcast to its own ID.
    target_id = instance.id
    if not target_id or not hasattr(instance, 'status_id'):
        return

    transmitter = Dopamine(spike_id=target_id, status_id=instance.status_id)
    async_to_sync(fire_neurotransmitter)(transmitter)


# ==========================================
# 3. GLOBAL ENTITY SIGNALS
# ==========================================

def broadcast_global_entity(instance, entity_type):
    target_id = get_spike_id(instance)
    if not target_id:
        return

    transmitter = Acetylcholine(
        spike_id=target_id,
        key=f'{entity_type}_update',
        value={'id': str(instance.id), 'action': 'saved'},
    )
    async_to_sync(fire_neurotransmitter)(transmitter)


@receiver(post_save, sender=PFCEpic)
@receiver(post_save, sender=PFCStory)
@receiver(post_save, sender=PFCTask)
def broadcast_pfc_updates(sender, instance, **kwargs):
    broadcast_global_entity(instance, 'pfc_ticket')


@receiver(post_save, sender=IdentityDisc)
def broadcast_identity_updates(sender, instance, **kwargs):
    broadcast_global_entity(instance, 'identity_disc')


@receiver(post_save, sender=Iteration)
@receiver(post_save, sender=IterationShift)
@receiver(post_save, sender=IterationShiftParticipant)
def broadcast_temporal_updates(sender, instance, **kwargs):
    broadcast_global_entity(instance, 'temporal_matrix')


@receiver(spawn_failed)
def on_spawn_failed(sender, spike_train, **kwargs):
    logger.error(f"Spawn failed signal caught for SpikeTrain: {spike_train.id}")


@receiver(spawn_success)
def on_spawn_success(sender, spike_train, **kwargs):
    logger.info(f"Spawn success signal caught for SpikeTrain: {spike_train.id}")