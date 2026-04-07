"""ElevenLabs REST TTS provider."""

import asyncio
import logging
import os
import tempfile
from typing import Any, Optional

import requests

from vocal_cortex.contracts import SynthesisResult, failure_result, success_result

logger = logging.getLogger('vocal_cortex')

ELEVENLABS_TTS_URL = (
    'https://api.elevenlabs.io/v1/text-to-speech/%s'
)


async def synthesize(
    text: str,
    *,
    provider_name: str,
    provider_config: dict[str, Any],
    voice: Optional[str] = None,
) -> SynthesisResult:
    """Synthesize via ElevenLabs HTTP API (blocking call in thread pool)."""
    api_key = (
        os.getenv('ELEVENLABS_API_KEY', '').strip()
        or (provider_config.get('api_key') or '').strip()
    )
    if not api_key:
        return failure_result(
            provider_name,
            'ElevenLabs API key not configured.',
        )

    voice_id = (
        (voice or '').strip()
        or (provider_config.get('voice_id') or '').strip()
    )
    if not voice_id:
        return failure_result(provider_name, 'ElevenLabs voice_id not configured.')

    model_id = (provider_config.get('model_id') or 'eleven_multilingual_v2').strip()
    url = ELEVENLABS_TTS_URL % (voice_id,)

    headers = {
        'xi-api-key': api_key,
        'Content-Type': 'application/json',
    }
    payload = {
        'text': text,
        'model_id': model_id,
    }

    def _post() -> requests.Response:
        return requests.post(url, headers=headers, json=payload, timeout=120)

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, _post)
    except Exception as exc:
        logger.exception('[VocalCortex] ElevenLabs request failed.')
        return failure_result(provider_name, 'ElevenLabs error: %s' % (exc,))

    if response.status_code >= 400:
        return failure_result(
            provider_name,
            'ElevenLabs HTTP %s: %s'
            % (response.status_code, response.text[:500]),
        )

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
    try:
        tmp.write(response.content)
        tmp.flush()
        path = tmp.name
    finally:
        tmp.close()

    return success_result(
        provider_name,
        path,
        format='mp3',
        voice_name=voice_id,
    )
