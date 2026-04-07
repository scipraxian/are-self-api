"""Voxtral TTS subprocess and model path resolution (vocal_cortex)."""

import logging
import os
import subprocess
from typing import Any

from auditory_cortex.providers.voxtral_runtime import (
    DEFAULT_MODELS_ROOT,
    resolve_binary,
)

from vocal_cortex.contracts import SynthesisResult, failure_result, success_result

logger = logging.getLogger('vocal_cortex')


def resolve_tts_model(cfg: dict[str, Any]) -> str:
    """Resolve TTS model path: env VOXTRAL_TTS_MODEL > config > default."""
    env_val = os.getenv('VOXTRAL_TTS_MODEL', '').strip()
    if env_val:
        return env_val
    cfg_val = (cfg.get('tts_model') or '').strip()
    if cfg_val:
        return cfg_val
    return os.path.join(DEFAULT_MODELS_ROOT, 'voxtral-tts')


def synthesize_with_voxtral(
    text: str,
    output_path: str,
    provider_name: str,
    provider_config: dict[str, Any],
) -> SynthesisResult:
    """Run Voxtral TTS subprocess to write audio at output_path."""
    binary = resolve_binary(provider_config)
    if not binary:
        return failure_result(provider_name, 'Voxtral binary not found.')

    model_path = resolve_tts_model(provider_config)
    timeout_seconds = int(provider_config.get('timeout_seconds') or 300)

    try:
        result = subprocess.run(
            [
                binary,
                'tts',
                '--text',
                text,
                '--out',
                output_path,
                '--model',
                model_path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return failure_result(provider_name, str(exc))

    if result.returncode != 0:
        err = (result.stderr or result.stdout or 'voxtral tts failed').strip()
        return failure_result(provider_name, err)

    if not os.path.isfile(output_path):
        return failure_result(
            provider_name,
            'voxtral TTS completed but output file missing: %s' % (output_path,),
        )

    return success_result(
        provider_name,
        output_path,
        format='wav',
        voice_name=None,
    )
