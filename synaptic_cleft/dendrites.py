import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class SynapticDendrite(AsyncWebsocketConsumer):
    """
    The UI's connection point. Binds to a specific Entity Class (Receptor)
    and listens for state updates.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.receptor_class = type[str]
        self.cleft_group = type[str]

    async def connect(self):
        # The URL route should now capture the model name: ws/synapse/(?P<receptor_class>\w+)/
        self.receptor_class = self.scope['url_route']['kwargs'][
            'receptor_class'
        ].lower()
        self.cleft_group = f'synapse_{self.receptor_class}'

        await self.channel_layer.group_add(self.cleft_group, self.channel_name)
        await self.accept()
        logger.info(f'Dendrite bound to receptor group: {self.cleft_group}')

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.cleft_group, self.channel_name
        )
        logger.info(
            f'Dendrite detached from receptor group: {self.cleft_group}'
        )

    async def release_neurotransmitter(self, event):
        """Catches the payload from the axon hillock and pushes to the client."""
        payload = event.get('payload', {})
        await self.send(text_data=json.dumps(payload))
