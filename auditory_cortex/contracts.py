"""Pydantic contracts for speech-to-text results."""

from typing import Optional

from pydantic import BaseModel


class TranscriptionResult(BaseModel):
    """Structured result from an STT provider."""

    success: bool
    text: str = ''
    provider: str
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


def failure_result(provider: str, error_message: str) -> TranscriptionResult:
    """Build a typed STT failure per Layer 4 error table (empty text, error set)."""
    return TranscriptionResult(
        success=False,
        text='',
        provider=provider,
        error=error_message,
    )


def success_result(
    provider: str,
    text: str,
    *,
    language: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> TranscriptionResult:
    """Build a successful transcription result."""
    return TranscriptionResult(
        success=True,
        text=text,
        provider=provider,
        language=language,
        duration_seconds=duration_seconds,
        error=None,
    )
