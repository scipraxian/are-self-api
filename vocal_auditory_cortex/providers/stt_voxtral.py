"""Voxtral local STT provider."""

import asyncio
from typing import Any

from vocal_auditory_cortex.contracts import TranscriptionResult
from vocal_auditory_cortex.providers import voxtral_runtime


async def transcribe(
    audio_path: str,
    *,
    provider_name: str,
    provider_config: dict[str, Any],
) -> TranscriptionResult:
    """Transcribe using Voxtral CLI subprocess (see voxtral_runtime)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        voxtral_runtime.transcribe_with_voxtral,
        audio_path,
        provider_name,
        provider_config,
    )
