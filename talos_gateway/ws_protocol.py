"""WebSocket message types for the local gateway CLI."""

from typing import Any

from django.utils import timezone

from talos_gateway.contracts import PlatformEnvelope

WS_PROTOCOL_VERSION = 1

WS_MSG_INBOUND = 'inbound'
WS_MSG_INBOUND_ACK = 'inbound_ack'
WS_MSG_ERROR = 'error'
WS_MSG_TOKEN_DELTA = 'token_delta'
WS_MSG_JOIN_SESSION = 'join_session'
WS_MSG_JOIN_SESSION_ACK = 'join_session_ack'
WS_MSG_RESPONSE_COMPLETE = 'response_complete'
WS_MSG_SESSION_STATUS = 'session_status'
WS_MSG_INTERRUPT = 'interrupt'
WS_MSG_INTERRUPT_ACK = 'interrupt_ack'
WS_MSG_LIST_SESSIONS = 'list_sessions'
WS_MSG_LIST_SESSIONS_ACK = 'list_sessions_ack'
WS_MSG_CREATE_SESSION = 'create_session'
WS_MSG_CREATE_SESSION_ACK = 'create_session_ack'

WS_ERR_NO_GATEWAY = 'gateway_unavailable'
WS_ERR_INVALID_JSON = 'invalid_json'
WS_ERR_VALIDATION = 'validation_error'
WS_ERR_UNKNOWN_TYPE = 'unknown_message_type'

CLI_PLATFORM = 'cli'

DEFAULT_SENDER_ID = 'cli'
DEFAULT_SENDER_NAME = 'CLI'


def platform_envelope_from_inbound_payload(
    data: dict[str, Any],
) -> PlatformEnvelope:
    """Build ``PlatformEnvelope`` from validated inbound WebSocket JSON."""
    if data.get('type') != WS_MSG_INBOUND:
        raise ValueError('message type must be inbound')

    channel_id = data.get('channel_id')
    message_id = data.get('message_id')

    if not channel_id or not isinstance(channel_id, str):
        raise ValueError('channel_id is required and must be a string')

    if message_id is None or message_id == '':
        raise ValueError('message_id is required')

    content = data.get('content')
    if content is None or not isinstance(content, str):
        raise ValueError('content is required and must be a string')

    sender_id = data.get('sender_id') or DEFAULT_SENDER_ID
    sender_name = data.get('sender_name') or DEFAULT_SENDER_NAME

    if not isinstance(sender_id, str) or not isinstance(sender_name, str):
        raise ValueError('sender_id and sender_name must be strings when set')

    thread_id = data.get('thread_id')
    if thread_id is not None and not isinstance(thread_id, str):
        raise ValueError('thread_id must be a string or null')

    reply_to = data.get('reply_to')
    if reply_to is not None and not isinstance(reply_to, str):
        raise ValueError('reply_to must be a string or null')

    identity_disc_id = data.get('identity_disc_id')
    if identity_disc_id is not None and not isinstance(identity_disc_id, str):
        raise ValueError('identity_disc_id must be a string or null')
    if isinstance(identity_disc_id, str) and not identity_disc_id:
        identity_disc_id = None

    return PlatformEnvelope(
        platform=CLI_PLATFORM,
        channel_id=channel_id,
        thread_id=thread_id,
        sender_id=sender_id,
        sender_name=sender_name,
        message_id=str(message_id),
        content=content,
        identity_disc_id=identity_disc_id,
        reply_to=reply_to,
        timestamp=timezone.now(),
    )
