import asyncio
import logging
import os

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

# Voices available to agents. Slug → Piper model name.
# Keep this list small and memorable for 7B models.
VOICE_CATALOG = {
    'male': 'en_US-lessac-medium',
    'female': 'en_US-amy-medium',
    'child': 'en_US-hfc_female-medium',
    'narrator': 'en_US-joe-medium',
    'whisper': 'en_US-lessac-low',
}

DEFAULT_VOICE = 'male'

# Environment context variable key for audio output directory.
AUDIO_ROOT_KEY = 'audio_root'


async def mcp_tts(
    text: str,
    filename: str = 'output.wav',
    voice: str = DEFAULT_VOICE,
    thought: str = '',
    session_id: str = None,
    turn_id: int = None,
    **kwargs,
) -> str:
    """
    MCP Tool: Text-to-Speech via Piper TTS.

    Converts text to speech and saves a WAV file. The output directory
    comes from the environment's audio_root context variable.
    Runs entirely locally — no GPU, no API keys, no internet.

    Available voices: male, female, child, narrator, whisper.

    Args:
        text: The text to convert to speech.
        filename: Name for the output file (default: output.wav).
        voice: Voice slug — one of: male, female, child, narrator, whisper.
        thought: Your reasoning for generating this audio.
        session_id: Injected automatically by the Parietal Lobe gateway.
        turn_id: Injected automatically by the Parietal Lobe gateway.
    """
    if not text or not text.strip():
        return 'ERROR: No text provided for speech synthesis.'

    # Resolve voice slug to Piper model name
    voice_key = voice.lower().strip()
    piper_model = VOICE_CATALOG.get(voice_key)
    if not piper_model:
        slugs = ', '.join(VOICE_CATALOG.keys())
        return (
            f'ERROR: Unknown voice "{voice}". '
            f'Available voices: {slugs}'
        )

    # Resolve output directory from environment context variable
    output_dir = await _resolve_audio_root(session_id)
    if not output_dir:
        return (
            f'ERROR: No "{AUDIO_ROOT_KEY}" context variable configured '
            f'on the active environment. Add it in the Environment Editor.'
        )

    # Sanitize filename
    if not filename.lower().endswith('.wav'):
        filename = filename + '.wav'

    output_path = os.path.join(output_dir, filename)

    try:
        await asyncio.to_thread(os.makedirs, output_dir, exist_ok=True)
    except OSError as e:
        return f'ERROR: Could not create output directory {output_dir}: {e}'

    try:
        from piper.voice import PiperVoice  # noqa: F401
    except ImportError:
        return (
            'ERROR: piper-tts is not installed. '
            'Install with: pip install piper-tts'
        )

    try:
        result = await asyncio.to_thread(
            _synthesize, text, output_path, piper_model
        )
        return result
    except FileNotFoundError:
        return (
            f'ERROR: Voice model "{piper_model}" not found. '
            f'Download from https://github.com/rhasspy/piper/blob/master/VOICES.md'
        )
    except Exception as e:
        logger.exception('[ParietalLobe] mcp_tts failed: %s', e)
        return f'ERROR: Speech synthesis failed: {e}'


async def _resolve_audio_root(session_id: str) -> str:
    """Look up the audio_root context variable from the active environment."""
    if not session_id:
        return ''

    try:
        from environments.models import ProjectEnvironment

        env = await sync_to_async(
            ProjectEnvironment.objects.filter(selected=True)
            .prefetch_related('contexts__key')
            .first
        )()
        if not env:
            return ''

        contexts = await sync_to_async(
            lambda: list(env.contexts.select_related('key').all())
        )()
        for ctx in contexts:
            if ctx.key and ctx.key.name == AUDIO_ROOT_KEY:
                return ctx.value
        return ''
    except Exception as e:
        logger.warning('[ParietalLobe] Could not resolve %s: %s', AUDIO_ROOT_KEY, e)
        return ''


def _synthesize(text: str, output_path: str, piper_model: str) -> str:
    """Blocking Piper synthesis — runs in a thread via asyncio.to_thread."""
    import wave

    from piper.voice import PiperVoice

    piper_voice = PiperVoice.load(piper_model)

    with wave.open(output_path, 'wb') as wav_file:
        piper_voice.synthesize(text, wav_file)

    file_size = os.path.getsize(output_path)
    size_str = (
        f'{file_size / 1024:.1f} KB'
        if file_size < 1024 * 1024
        else f'{file_size / (1024 * 1024):.1f} MB'
    )

    return (
        f'Speech synthesized successfully.\n'
        f'File: {output_path}\n'
        f'Size: {size_str}\n'
        f'Voice: {piper_model}\n'
        f'Text length: {len(text)} characters'
    )
