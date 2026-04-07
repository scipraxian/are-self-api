"""Local faster-whisper STT provider (no remote retry at service layer)."""

import asyncio
import logging
from typing import Any

from auditory_cortex.contracts import TranscriptionResult, failure_result, success_result

logger = logging.getLogger('auditory_cortex')

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore[misc, assignment]


def _transcribe_sync(
    audio_path: str,
    provider_name: str,
    provider_config: dict[str, Any],
) -> TranscriptionResult:
    """Run Whisper in a worker thread."""
    if WhisperModel is None:
        logger.error('[AuditoryCortex] faster_whisper package is not installed.')
        return failure_result(
            provider_name,
            'faster_whisper package is not installed.',
        )

    model_name = (provider_config.get('model') or 'base').strip()
    device = (provider_config.get('device') or 'cpu').strip()
    compute_type = (provider_config.get('compute_type') or 'int8').strip()

    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        segments, info = model.transcribe(audio_path)
        parts = [segment.text for segment in segments]
        text = ''.join(parts).strip()
        return success_result(
            provider_name,
            text,
            language=getattr(info, 'language', None),
            duration_seconds=getattr(info, 'duration', None),
        )
    except Exception as exc:
        logger.exception('[AuditoryCortex] faster_whisper transcribe failed.')
        return failure_result(provider_name, 'faster_whisper error: %s' % (exc,))


async def transcribe(
    audio_path: str,
    *,
    provider_name: str,
    provider_config: dict[str, Any],
) -> TranscriptionResult:
    """Transcribe audio file using faster-whisper (CPU/GPU per config)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        _transcribe_sync,
        audio_path,
        provider_name,
        provider_config,
    )
