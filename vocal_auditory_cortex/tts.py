"""Text-to-speech service: provider dispatch, cache, and retry (Layer 4)."""

import asyncio
import hashlib
import importlib
import logging
import os
import shutil
from types import ModuleType
from typing import Any, Optional

from django.conf import settings

from vocal_auditory_cortex.contracts import (
    SynthesisResult,
    tts_failure_result,
    tts_success_result,
)

logger = logging.getLogger('vocal_auditory_cortex')

LOCAL_TTS_PROVIDER_NAMES = frozenset({'voxtral'})

REMOTE_RETRY_DELAY_SECONDS = 2
MAX_REMOTE_ATTEMPTS = 2


def _is_local_provider(provider_name: str) -> bool:
    """Return True if this TTS provider must not use remote retry policy."""
    return provider_name in LOCAL_TTS_PROVIDER_NAMES


def _cache_key(provider_name: str, voice: Optional[str], text: str) -> str:
    """Stable hash for TTS cache filename."""
    raw = '%s|%s|%s' % (provider_name, voice or '', text)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return digest


def _cached_audio_path(
    cache_dir: str, provider_name: str, voice: Optional[str], text: str
) -> str:
    """Return path to cached audio file for this synthesis key."""
    name = _cache_key(provider_name, voice, text) + '.bin'
    return os.path.join(cache_dir, name)


def _load_tts_module(provider_name: str) -> ModuleType:
    """Import vocal_auditory_cortex.providers.tts_<provider_name>."""
    module_path = 'vocal_auditory_cortex.providers.tts_%s' % (provider_name,)
    return importlib.import_module(module_path)


async def _call_provider_synthesize(
    provider_name: str,
    provider_config: dict[str, Any],
    text: str,
    voice: Optional[str],
) -> SynthesisResult:
    """Load provider module and await its synthesize() entrypoint."""
    module = _load_tts_module(provider_name)
    synthesize_fn = getattr(module, 'synthesize')
    return await synthesize_fn(
        text,
        provider_name=provider_name,
        provider_config=provider_config,
        voice=voice,
    )


class TTSService(object):
    """Dispatches synthesis to configured TTS provider.

    Uses optional file cache when ``tts_cache_dir`` is set.
    """

    def __init__(self, service_settings: Optional[dict[str, Any]] = None):
        """If service_settings is None, use django.conf.settings.VOCAL_CORTEX."""
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

    def _read_cache_if_present(
        self,
        provider_name: str,
        voice: Optional[str],
        text: str,
    ) -> Optional[SynthesisResult]:
        """Return cached SynthesisResult if cache file exists."""
        cache_dir = (self._settings.get('tts_cache_dir') or '').strip()
        if not cache_dir:
            return None
        if not os.path.isdir(cache_dir):
            return None
        path = _cached_audio_path(cache_dir, provider_name, voice, text)
        if os.path.isfile(path):
            logger.info(
                '[VocalAuditoryCortex] TTS cache hit for provider %s.', provider_name
            )
            return tts_success_result(
                provider_name,
                path,
                format='cached',
                voice_name=voice,
            )
        return None

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> SynthesisResult:
        """Synthesize text using VOCAL_CORTEX['tts_provider']."""
        if not self._settings.get('enabled', True):
            return tts_failure_result('tts', 'TTS is disabled in settings.')

        provider_name = (self._settings.get('tts_provider') or '').strip()
        if not provider_name:
            return tts_failure_result('tts', 'No tts_provider configured.')

        cached = self._read_cache_if_present(provider_name, voice, text)
        if cached is not None:
            return cached

        provider_config = self._provider_config(provider_name)
        local = _is_local_provider(provider_name)

        last_result: Optional[SynthesisResult] = None
        attempts = 1 if local else MAX_REMOTE_ATTEMPTS

        for attempt in range(attempts):
            try:
                result = await _call_provider_synthesize(
                    provider_name,
                    provider_config,
                    text,
                    voice,
                )
            except Exception as exc:
                logger.exception(
                    '[VocalAuditoryCortex] TTS provider %s raised on attempt %s.',
                    provider_name,
                    attempt + 1,
                )
                result = tts_failure_result(
                    provider_name,
                    'TTS provider error: %s' % (exc,),
                )

            last_result = result

            if result.success and result.audio_path:
                self._write_to_cache_if_configured(
                    provider_name,
                    voice,
                    text,
                    result.audio_path,
                )

            if result.success:
                return result

            if local:
                logger.warning(
                    '[VocalAuditoryCortex] Local TTS provider %s failed: %s',
                    provider_name,
                    result.error,
                )
                return result

            if attempt + 1 < attempts:
                logger.info(
                    '[VocalAuditoryCortex] Retrying TTS provider %s after %ss.',
                    provider_name,
                    REMOTE_RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(REMOTE_RETRY_DELAY_SECONDS)

        assert last_result is not None
        return last_result

    def _write_to_cache_if_configured(
        self,
        provider_name: str,
        voice: Optional[str],
        text: str,
        audio_path: str,
    ) -> None:
        """Copy synthesized file into tts_cache_dir when configured."""
        cache_dir = (self._settings.get('tts_cache_dir') or '').strip()
        if not cache_dir:
            return
        os.makedirs(cache_dir, exist_ok=True)
        dest = _cached_audio_path(cache_dir, provider_name, voice, text)
        try:
            shutil.copy2(audio_path, dest)
        except OSError as exc:
            logger.warning(
                '[VocalAuditoryCortex] Could not write TTS cache: %s', exc
            )
