import logging

from channels.layers import get_channel_layer

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

    # e.g., "synapse_identitydisc" or "synapse_chatmessage"
    group_name = f'synapse_{str(transmitter.receptor_class).lower()}'

    try:
        await channel_layer.group_send(
            group_name, transmitter.to_synapse_dict()
        )
    except Exception as e:
        logger.error(
            f'Failed to fire neurotransmitter {transmitter.receptor_class} '
            f'for dendrite {transmitter.dendrite_id}: {e}',
            exc_info=True,
        )
