import json
import logging
from uuid import UUID

from channels.generic.websocket import AsyncWebsocketConsumer

from .constants import SYNAPSE_GROUP_PREFIX

logger = logging.getLogger(__name__)


class SynapticDendrite(AsyncWebsocketConsumer):
    """
    The UI's connection point. Binds to a specific Spike's synaptic cleft
    and listens for neurotransmitters.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spike_id = type[UUID]
        self.cleft_group = type[str]

    async def connect(self):
        self.spike_id = self.scope['url_route']['kwargs']['spike_id']
        self.cleft_group = f'{SYNAPSE_GROUP_PREFIX}{self.spike_id}'

        await self.channel_layer.group_add(self.cleft_group, self.channel_name)

        await self.accept()
        logger.debug(f'Dendrite bound to cleft: {self.cleft_group}')

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.cleft_group, self.channel_name
        )
        logger.debug(f'Dendrite detached from cleft: {self.cleft_group}')

    async def release_neurotransmitter(self, event):
        """
        Catches the payload from the axon hillock and pushes to the client.
        Must match the RELEASE_METHOD constant exactly.
        """
        payload = event.get('payload', {})
        await self.send(text_data=json.dumps(payload))
