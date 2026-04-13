"""Django signals for gateway outbound completion events.

When a ReasoningSession transitions to ATTENTION_REQUIRED or COMPLETED,
broadcast the last assistant response to the session's Channels group so
that connected WebSocket clients receive a ``response_complete`` event.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver

from frontal_lobe.channels_streaming import reasoning_session_group_name
from frontal_lobe.models import ReasoningSession, ReasoningStatusID

logger = logging.getLogger('talos_gateway.signals')

_BROADCAST_STATUSES = frozenset({
    ReasoningStatusID.ATTENTION_REQUIRED,
    ReasoningStatusID.COMPLETED,
})


def _extract_assistant_content(session: ReasoningSession) -> str:
    """Return the assistant text from the most recent ReasoningTurn.

    Handles both direct ``{role, content}`` and OpenAI-style
    ``{choices: [{message: {...}}]}`` response payloads.
    """
    last_turn = session.turns.order_by('-turn_number').first()
    if last_turn is None:
        return ''

    payload = last_turn.response_payload
    if payload is None:
        return ''

    if 'role' in payload:
        return payload.get('content', '')

    choices = payload.get('choices', [])
    if choices:
        return choices[0].get('message', {}).get('content', '')

    return ''


@receiver(post_save, sender=ReasoningSession)
def broadcast_response_complete(sender, instance, update_fields=None, **kwargs):
    """Broadcast response_complete to the session's Channels group.

    Only fires when ``status_id`` is in the set of broadcast-worthy statuses
    AND the save actually touched ``status_id`` (via ``update_fields``).
    """
    if update_fields is not None and 'status_id' not in update_fields:
        return

    if instance.status_id not in _BROADCAST_STATUSES:
        return

    layer = get_channel_layer()
    if layer is None:
        logger.warning(
            '[Gateway] channel_layer is None; cannot broadcast for session %s.',
            instance.pk,
        )
        return

    content = _extract_assistant_content(instance)
    group = reasoning_session_group_name(instance.pk)

    async_to_sync(layer.group_send)(
        group,
        {
            'type': 'response_complete',
            'content': content,
            'session_status': str(instance.status_id),
        },
    )

    logger.info(
        '[Gateway] Broadcast response_complete for session %s (status=%s).',
        instance.pk,
        instance.status_id,
    )
