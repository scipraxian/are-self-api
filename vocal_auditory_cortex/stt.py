"""Speech-to-text service: provider dispatch and retry policy (Layer 4)."""

import asyncio
import importlib
import logging
from types import ModuleType
from typing import Any, Optional

from django.conf import settings

from vocal_auditory_cortex.contracts import TranscriptionResult, stt_failure_result

logger = logging.getLogger('vocal_auditory_cortex')

LOCAL_STT_PROVIDER_NAMES = frozenset({'faster_whisper'})

REMOTE_RETRY_DELAY_SECONDS = 2
MAX_REMOTE_ATTEMPTS = 2


def _is_local_provider(provider_name: str) -> bool:
    """Return True if this STT provider must not use remote retry policy."""
    return provider_name in LOCAL_STT_PROVIDER_NAMES


def _load_stt_module(provider_name: str) -> ModuleType:
    """Import vocal_auditory_cortex.providers.stt_<provider_name>."""
    module_path = 'vocal_auditory_cortex.providers.stt_%s' % (provider_name,)
    return importlib.import_module(module_path)


async def _call_provider_transcribe(
    provider_name: str,
    provider_config: dict[str, Any],
    audio_path: str,
) -> TranscriptionResult:
    """Load provider module and await its transcribe() entrypoint."""
    module = _load_stt_module(provider_name)
    transcribe_fn = getattr(module, 'transcribe')
    return await transcribe_fn(
        audio_path,
        provider_name=provider_name,
        provider_config=provider_config,
    )


class STTService(object):
    """Dispatches transcription to configured STT provider with retry rules."""

    def __init__(self, service_settings: Optional[dict[str, Any]] = None):
        """Init from ``service_settings`` or ``settings.VOCAL_CORTEX``."""
        self._settings = service_settings
        if self._settings is None:
            self._settings = getattr(
                settings,
                'VOCAL_CORTEX',
                {},
            )

    def _provider_config(self, provider_name: str) -> dict[str, Any]:
        """Return the nested providers dict for one provider."""
        providers = self._settings.get('providers') or {}
        cfg = providers.get(provider_name)
        if cfg is None:
            return {}
        return dict(cfg)

    async def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Transcribe audio at path using VOCAL_CORTEX['stt_provider']."""
        if not self._settings.get('enabled', True):
            return stt_failure_result('stt', 'STT is disabled in settings.')

        provider_name = (self._settings.get('stt_provider') or '').strip()
        if not provider_name:
            return stt_failure_result('stt', 'No stt_provider configured.')

        provider_config = self._provider_config(provider_name)
        local = _is_local_provider(provider_name)

        last_result: Optional[TranscriptionResult] = None
        attempts = 1 if local else MAX_REMOTE_ATTEMPTS

        for attempt in range(attempts):
            try:
                result = await _call_provider_transcribe(
                    provider_name,
                    provider_config,
                    audio_path,
                )
            except Exception as exc:
                logger.exception(
                    '[VocalAuditoryCortex] STT provider %s raised on attempt %s.',
                    provider_name,
                    attempt + 1,
                )
                result = stt_failure_result(
                    provider_name,
                    'STT provider error: %s' % (exc,),
                )

            last_result = result
            if result.success:
                return result

            if local:
                logger.warning(
                    '[VocalAuditoryCortex] Local STT provider %s failed: %s',
                    provider_name,
                    result.error,
                )
                return result

            if attempt + 1 < attempts:
                logger.info(
                    '[VocalAuditoryCortex] Retrying STT provider %s after %ss.',
                    provider_name,
                    REMOTE_RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(REMOTE_RETRY_DELAY_SECONDS)

        assert last_result is not None
        return last_result
