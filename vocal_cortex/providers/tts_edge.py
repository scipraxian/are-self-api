"""Microsoft Edge TTS provider (edge-tts package)."""

import logging
import os
import tempfile
from typing import Any, Optional

from vocal_cortex.contracts import SynthesisResult, failure_result, success_result

logger = logging.getLogger('vocal_cortex')

try:
    import edge_tts
except ImportError:
    edge_tts = None  # type: ignore[misc, assignment]


async def synthesize(
    text: str,
    *,
    provider_name: str,
    provider_config: dict[str, Any],
    voice: Optional[str] = None,
) -> SynthesisResult:
    """Synthesize via edge-tts (network)."""
    if edge_tts is None:
        logger.error('[VocalCortex] edge_tts package is not installed.')
        return failure_result(
            provider_name,
            'edge_tts package is not installed.',
        )

    voice_name = voice or (provider_config.get('voice') or 'en-US-AriaNeural')
    communicate = edge_tts.Communicate(text, voice_name)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
    tmp.close()
    out_path = tmp.name
    try:
        await communicate.save(out_path)
    except Exception as exc:
        logger.exception('[VocalCortex] edge_tts save failed.')
        if os.path.isfile(out_path):
            try:
                os.unlink(out_path)
            except OSError:
                pass
        return failure_result(provider_name, 'edge_tts error: %s' % (exc,))

    return success_result(
        provider_name,
        out_path,
        format='mp3',
        voice_name=voice_name,
    )
