"""Voxtral binary and subprocess helpers shared by STT (and referenced from TTS)."""

import logging
import os
import shutil
import subprocess
from typing import Any, Optional

from auditory_cortex.contracts import TranscriptionResult, failure_result, success_result

logger = logging.getLogger('auditory_cortex')

_VOXTRAL_EXE_RAW = 'voxtral'
_VOXTRAL_EXE_LINUX = '/usr/local/bin/voxtral'
_VOXTRAL_EXE_WIN = 'C:/Program Files/Voxtral/voxtral.exe'

DEFAULT_MODELS_ROOT = os.path.expanduser('~/.cache/talos/voxtral_models')


def resolve_binary(cfg: dict[str, Any]) -> Optional[str]:
    """Return path to voxtral binary, or None if not found."""
    env_bin = os.getenv('VOXTRAL_BINARY', '').strip()
    if env_bin and os.path.isfile(env_bin):
        return env_bin
    cfg_bin = (cfg.get('binary') or '').strip()
    if cfg_bin and os.path.isfile(cfg_bin):
        return cfg_bin
    for candidate in (_VOXTRAL_EXE_LINUX, _VOXTRAL_EXE_WIN):
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which(_VOXTRAL_EXE_RAW)
    if found:
        return found
    return None


def resolve_asr_model(cfg: dict[str, Any]) -> str:
    """Resolve ASR model path: env VOXTRAL_ASR_MODEL > config > default."""
    env_val = os.getenv('VOXTRAL_ASR_MODEL', '').strip()
    if env_val:
        return env_val
    cfg_val = (cfg.get('asr_model') or '').strip()
    if cfg_val:
        return cfg_val
    return os.path.join(DEFAULT_MODELS_ROOT, 'voxtral')


def convert_to_wav_if_needed(file_path: str) -> Optional[str]:
    """Convert non-WAV audio to 16kHz mono WAV when ffmpeg exists."""
    if os.path.splitext(file_path)[1].lower() == '.wav':
        return file_path
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return None
    out_path = file_path.rsplit('.', 1)[0] + '_voxtral_input.wav'
    try:
        subprocess.run(
            [ffmpeg, '-y', '-i', file_path, '-ar', '16000', '-ac', '1', out_path],
            capture_output=True,
            timeout=60,
            check=True,
        )
        return out_path
    except (OSError, subprocess.SubprocessError):
        return None


def run_asr_subprocess(
    binary_path: str,
    audio_path: str,
    model_path: str,
    timeout_seconds: int,
) -> tuple[bool, str, str]:
    """Run Voxtral ASR; return (ok, stdout_or_transcript, error_message)."""
    try:
        result = subprocess.run(
            [binary_path, 'asr', '--audio', audio_path, '--model', model_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, '', str(exc)

    if result.returncode != 0:
        err = (result.stderr or result.stdout or 'voxtral asr failed').strip()
        return False, '', err
    return True, (result.stdout or '').strip(), ''


def transcribe_with_voxtral(
    audio_path: str,
    provider_name: str,
    provider_config: dict[str, Any],
) -> TranscriptionResult:
    """Synchronous Voxtral ASR entry used from stt_voxtral provider."""
    cfg = provider_config
    binary = resolve_binary(cfg)
    if not binary:
        return failure_result(provider_name, 'Voxtral binary not found.')

    model_path = resolve_asr_model(cfg)
    timeout_seconds = int(cfg.get('timeout_seconds') or 300)

    wav_path = convert_to_wav_if_needed(audio_path) or audio_path
    ok, text, err = run_asr_subprocess(
        binary,
        wav_path,
        model_path,
        timeout_seconds,
    )
    if not ok:
        return failure_result(provider_name, err)

    return success_result(provider_name, text, language=None, duration_seconds=None)
