"""Pydantic contracts for normalized platform I/O (Layer 4)."""

import base64
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_serializer


class Attachment(BaseModel):
    """Normalized media attachment for various platforms."""

    url: str
    filename: str
    content_type: str
    size_bytes: Optional[int] = None


class PlatformEnvelope(BaseModel):
    """Inbound message from any platform."""

    platform: str
    channel_id: str
    thread_id: Optional[str] = None
    sender_id: str
    sender_name: str
    message_id: str
    content: str
    attachments: list[Attachment] = Field(default_factory=list)
    voice_audio: Optional[bytes] = None
    reply_to: Optional[str] = None
    timestamp: datetime
    raw_event: Optional[dict[str, Any]] = None

    @field_serializer('voice_audio', when_used='json')
    def _serialize_voice_audio(
        self, value: Optional[bytes], _info: object
    ) -> Optional[str]:
        """Serialize raw audio as base64 after PCM in JSON mode."""
        if value is None:
            return None
        return base64.b64encode(value).decode('ascii')


class DeliveryPayload(BaseModel):
    """Outbound message to any platform."""

    platform: str
    channel_id: str
    thread_id: Optional[str] = None
    content: str
    media_paths: list[str] = Field(default_factory=list)
    voice_audio_path: Optional[str] = None
    reply_to: Optional[str] = None
    is_voice: bool = False
