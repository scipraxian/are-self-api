"""Pydantic contracts for speech-to-text and text-to-speech results."""

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


class SynthesisResult(BaseModel):
    """Structured result from a TTS provider."""

    success: bool
    audio_path: Optional[str] = None
    provider: str
    format: Optional[str] = None
    duration_seconds: Optional[float] = None
    voice_name: Optional[str] = None
    error: Optional[str] = None


def stt_failure_result(provider: str, error_message: str) -> TranscriptionResult:
    """Build a typed STT failure per Layer 4 error table.

    No transcript text; ``error`` is set.
    """
    return TranscriptionResult(
        success=False,
        text='',
        provider=provider,
        error=error_message,
    )


def stt_success_result(
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


def tts_failure_result(provider: str, error_message: str) -> SynthesisResult:
    """Build a typed TTS failure per Layer 4 error table.

    No audio path; ``error`` is set.
    """
    return SynthesisResult(
        success=False,
        audio_path=None,
        provider=provider,
        error=error_message,
    )


def tts_success_result(
    provider: str,
    audio_path: str,
    *,
    format: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    voice_name: Optional[str] = None,
) -> SynthesisResult:
    """Build a successful synthesis result."""
    return SynthesisResult(
        success=True,
        audio_path=audio_path,
        provider=provider,
        format=format,
        duration_seconds=duration_seconds,
        voice_name=voice_name,
        error=None,
    )
