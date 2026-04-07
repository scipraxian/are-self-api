"""Pydantic contracts for text-to-speech results."""

from typing import Optional

from pydantic import BaseModel


class SynthesisResult(BaseModel):
    """Structured result from a TTS provider."""

    success: bool
    audio_path: Optional[str] = None
    provider: str
    format: Optional[str] = None
    duration_seconds: Optional[float] = None
    voice_name: Optional[str] = None
    error: Optional[str] = None


def failure_result(provider: str, error_message: str) -> SynthesisResult:
    """Build a typed TTS failure per Layer 4 error table (no audio path, error set)."""
    return SynthesisResult(
        success=False,
        audio_path=None,
        provider=provider,
        error=error_message,
    )


def success_result(
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
