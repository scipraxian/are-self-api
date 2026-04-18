"""Inbound/outbound message mapping for gateway orchestrator."""

import logging
from typing import Any, Optional

from asgiref.sync import sync_to_async

from frontal_lobe.models import ReasoningSession
from talos_gateway.contracts import DeliveryPayload, PlatformEnvelope
from talos_gateway.models import GatewaySession
from talos_gateway.runtime import wake_reasoning
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
        """Queue user content and wake reasoning via the canonical path."""
        wake_result = await sync_to_async(wake_reasoning)(gateway_session, reasoning_session, envelope.content)
        await sync_to_async(reasoning_session.refresh_from_db)()
        queue = list(reasoning_session.swarm_message_queue or [])
        logger.debug(
            '[MessageRouter] Dispatched message for session %s (depth=%s, action=%s).',
            reasoning_session.pk,
            len(queue),
            wake_result.get('action'),
        )
        return {
            'success': True,
            'queue_depth': len(queue),
            'action': wake_result.get('action', ''),
            'session_id': str(reasoning_session.pk),
        }

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
