"""Optional Django Channels fan-out for LLM token deltas."""

import logging
from uuid import UUID

from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

GROUP_PREFIX = 'session_'


def reasoning_session_group_name(session_id: UUID) -> str:
    """Channels group name for a ReasoningSession token stream."""
    return '%s%s' % (GROUP_PREFIX, session_id)


class TokenChannelSender(object):
    """Async callback for SynapseClient.chat_stream / FrontalLobe.run streaming."""

    def __init__(self, session_id: UUID):
        self.session_id = session_id
        self._group = reasoning_session_group_name(session_id)

    async def __call__(self, token: str) -> None:
        """Send one token delta to all sockets in the session group."""
        layer = get_channel_layer()
        if layer is None:
            logger.warning(
                '[FrontalLobe] channel_layer is None; token not sent for session %s.',
                self.session_id,
            )
            return
        await layer.group_send(
            self._group,
            {'type': 'token_delta', 'token': token},
        )
