"""Inbound/outbound message mapping for gateway orchestrator."""

import logging
from typing import Any, Optional

from frontal_lobe.models import ReasoningSession
from talos_gateway.contracts import DeliveryPayload, PlatformEnvelope
from talos_gateway.models import GatewaySession
from talos_gateway.session_manager import SessionManager

logger = logging.getLogger('talos_gateway.message_router')


class MessageRouter(object):
    """Queue inbound text on ``ReasoningSession``; build outbound payloads."""

    def __init__(
        self, session_manager: Optional[SessionManager] = None
    ) -> None:
        self.session_manager = session_manager or SessionManager()

    async def dispatch_inbound(
        self,
        gateway_session: GatewaySession,
        reasoning_session: ReasoningSession,
        envelope: PlatformEnvelope,
    ) -> dict[str, Any]:
        """Append user content to ``swarm_message_queue``."""
        queue = list(reasoning_session.swarm_message_queue or [])
        queue.append(
            {
                'role': 'user',
                'content': envelope.content,
                'message_id': envelope.message_id,
                'sender_id': envelope.sender_id,
            }
        )
        reasoning_session.swarm_message_queue = queue
        reasoning_session.save(update_fields=['swarm_message_queue'])
        logger.debug(
            '[MessageRouter] Queued message for session %s (depth=%s).',
            reasoning_session.pk,
            len(queue),
        )
        return {'success': True, 'queue_depth': len(queue)}

    def build_delivery_payload(
        self,
        platform: str,
        channel_id: str,
        content: str,
        thread_id: Optional[str] = None,
        *,
        is_voice: bool = False,
        voice_audio_path: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> DeliveryPayload:
        """Build a ``DeliveryPayload`` for outbound text/voice."""
        return DeliveryPayload(
            platform=platform,
            channel_id=channel_id,
            thread_id=thread_id,
            content=content,
            is_voice=is_voice,
            voice_audio_path=voice_audio_path,
            reply_to=reply_to,
        )
