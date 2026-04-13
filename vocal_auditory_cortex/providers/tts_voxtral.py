"""Voxtral local TTS provider."""

import asyncio
import logging
import os
from typing import Any, Optional

from vocal_auditory_cortex.contracts import SynthesisResult
from vocal_auditory_cortex.providers import host_paths
from vocal_auditory_cortex.providers import voxtral_runtime

_log = logging.getLogger('vocal_auditory_cortex')


def _synthesize_sync(
    text: str,
    out_path: str,
    provider_name: str,
    provider_config: dict[str, Any],
) -> SynthesisResult:
    """Run Voxtral TTS in a worker thread."""
    return voxtral_runtime.synthesize_with_voxtral(
        text,
        out_path,
        provider_name,
        provider_config,
    )


async def synthesize(
    text: str,
    *,
    provider_name: str,
    provider_config: dict[str, Any],
    voice: Optional[str] = None,
) -> SynthesisResult:
    """Synthesize using local Voxtral TTS subprocess."""
    if voice:
        _log.debug(
            '[VocalAuditoryCortex] voxtral TTS voice override not used: %s', voice
        )
    loop = asyncio.get_running_loop()
    runtime = 'win' if os.name == 'nt' else 'posix'
    out_path = host_paths.provider_writable_temp(runtime, 'wav')
    return await loop.run_in_executor(
        None,
        _synthesize_sync,
        text,
        out_path,
        provider_name,
        provider_config,
    )
