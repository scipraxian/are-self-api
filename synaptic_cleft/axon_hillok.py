import logging

from channels.layers import get_channel_layer

from .constants import SYNAPSE_GROUP_PREFIX
from .neurotransmitters import Neurotransmitter

logger = logging.getLogger(__name__)


async def fire_neurotransmitter(transmitter: Neurotransmitter):
    """
    Releases a strongly-typed neurotransmitter into the synaptic cleft.
    """
    channel_layer = get_channel_layer()

    if not channel_layer:
        logger.warning('No channel layer found; neurotransmitter dropped.')
        return

    group_name = f'{SYNAPSE_GROUP_PREFIX}{transmitter.spike_id}'

    try:
        await channel_layer.group_send(
            group_name, transmitter.to_synapse_dict()
        )
    except Exception as e:
        logger.error(
            f'Failed to fire neurotransmitter {transmitter.event.value} '
            f'for spike {transmitter.spike_id}: {e}',
            exc_info=True,
        )
