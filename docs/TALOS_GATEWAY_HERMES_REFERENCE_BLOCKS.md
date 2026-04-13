# Talos Gateway: Hermes Reference Code Blocks Worth Reusing

Date: 2026-04-03
Author: Julianna
Status: Reference notes for Layer 4 implementation

Purpose:
- Preserve the small pieces of Hermes platform logic that are genuinely useful
- Avoid porting Hermes gateway architecture wholesale
- Give Talos developers exact source locations and porting guidance

Principle:
- Reuse platform truth, not Hermes architecture
- Do NOT port gateway/run.py, adapter class structure, session model, or AIAgent coupling
- DO selectively port utility logic that solves platform-specific edge cases

-------------------------------------------------------------------------------
1. High-value code blocks to preserve
-------------------------------------------------------------------------------

These are the Hermes code blocks most worth reusing for talos_gateway:

1. Message chunking that preserves fenced code blocks and inline code spans
2. MEDIA:/path extraction and [[audio_as_voice]] parsing
3. Local media/document cache helpers with retry and path safety
4. Discord voice-message metadata generation (duration + waveform)
5. Telegram MarkdownV2 escaping/stripping helpers
6. Target parsing for thread/topic-aware outbound delivery
7. Mirror text summaries for media-only sends

What is NOT worth porting directly:
- BasePlatformAdapter inheritance model
- Hermes gateway lifecycle and agent cache
- Platform adapter class shape
- Config loading from ~/.hermes/config.yaml
- Session store / mirroring / cron duplicate suppression as-is

-------------------------------------------------------------------------------
2. Message chunking with code-fence preservation
-------------------------------------------------------------------------------

Why this matters:
Long LLM responses often contain fenced code blocks. Naive chunking breaks the
markdown, especially on Telegram and Discord. Hermes has a solid implementation
that closes and reopens code fences when a chunk split lands inside a block.

Source:
- ~/.hermes/hermes-agent/gateway/platforms/base.py:1410-1519

Suggested Talos destination:
- talos_gateway/delivery.py
- or talos_gateway/adapters/base_patterns.py

Reference block:

```python
@staticmethod
def truncate_message(content: str, max_length: int = 4096) -> List[str]:
    """
    Split a long message into chunks, preserving code block boundaries.

    When a split falls inside a triple-backtick code block, the fence is
    closed at the end of the current chunk and reopened (with the original
    language tag) at the start of the next chunk. Multi-chunk responses
    receive indicators like ``(1/3)``.
    """
    if len(content) <= max_length:
        return [content]

    INDICATOR_RESERVE = 10
    FENCE_CLOSE = "\n```"

    chunks: List[str] = []
    remaining = content
    carry_lang: Optional[str] = None

    while remaining:
        prefix = f"```{carry_lang}\n" if carry_lang is not None else ""
        headroom = max_length - INDICATOR_RESERVE - len(prefix) - len(FENCE_CLOSE)
        if headroom < 1:
            headroom = max_length // 2

        if len(prefix) + len(remaining) <= max_length - INDICATOR_RESERVE:
            chunks.append(prefix + remaining)
            break

        region = remaining[:headroom]
        split_at = region.rfind("\n")
        if split_at < headroom // 2:
            split_at = region.rfind(" ")
        if split_at < 1:
            split_at = headroom

        candidate = remaining[:split_at]
        backtick_count = candidate.count("`") - candidate.count("\\`")
        if backtick_count % 2 == 1:
            last_bt = candidate.rfind("`")
            while last_bt > 0 and candidate[last_bt - 1] == "\\":
                last_bt = candidate.rfind("`", 0, last_bt)
            if last_bt > 0:
                safe_split = candidate.rfind(" ", 0, last_bt)
                nl_split = candidate.rfind("\n", 0, last_bt)
                safe_split = max(safe_split, nl_split)
                if safe_split > headroom // 4:
                    split_at = safe_split

        chunk_body = remaining[:split_at]
        remaining = remaining[split_at:].lstrip()
        full_chunk = prefix + chunk_body

        in_code = carry_lang is not None
        lang = carry_lang or ""
        for line in chunk_body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code:
                    in_code = False
                    lang = ""
                else:
                    in_code = True
                    tag = stripped[3:].strip()
                    lang = tag.split()[0] if tag else ""

        if in_code:
            full_chunk += FENCE_CLOSE
            carry_lang = lang
        else:
            carry_lang = None

        chunks.append(full_chunk)

    if len(chunks) > 1:
        total = len(chunks)
        chunks = [f"{chunk} ({i + 1}/{total})" for i, chunk in enumerate(chunks)]

    return chunks
```

Porting note:
- Keep the algorithm, but move it into a Talos utility module
- Make chunk indicator optional per platform if needed
- Consider returning richer metadata later, e.g. `ChunkedMessage(parts=[...])`

-------------------------------------------------------------------------------
3. MEDIA tag extraction and voice directive parsing
-------------------------------------------------------------------------------

Why this matters:
Hermes uses two compact conventions in generated text:
- `MEDIA:/path/to/file.ext`
- `[[audio_as_voice]]`

That is a clean pattern for Talos too. It lets FrontalLobe or tools return a
single text payload that includes attachment directives, while the gateway strips
those tags and delivers the referenced files natively.

Source:
- ~/.hermes/hermes-agent/gateway/platforms/base.py:768-807

Suggested Talos destination:
- talos_gateway/delivery.py

Reference block:

```python
@staticmethod
def extract_media(content: str) -> Tuple[List[Tuple[str, bool]], str]:
    """
    Extract MEDIA:<path> tags and [[audio_as_voice]] directives from response text.
    """
    media = []
    cleaned = content

    has_voice_tag = "[[audio_as_voice]]" in content
    cleaned = cleaned.replace("[[audio_as_voice]]", "")

    media_pattern = re.compile(
        r'''[`"']?MEDIA:\s*(?P<path>`[^`\n]+`|"[^"\n]+"|'[^'\n]+'|(?:~/|/)\S+(?:[^\S\n]+\S+)*?\.(?:png|jpe?g|gif|webp|mp4|mov|avi|mkv|webm|ogg|opus|mp3|wav|m4a)(?=[\s`"',;:)\]}]|$)|\S+)[`"']?'''
    )
    for match in media_pattern.finditer(content):
        path = match.group("path").strip()
        if len(path) >= 2 and path[0] == path[-1] and path[0] in "`\"'":
            path = path[1:-1].strip()
        path = path.lstrip("`\"'").rstrip("`\"',.;:)}]")
        if path:
            media.append((path, has_voice_tag))

    if media:
        cleaned = media_pattern.sub('', cleaned)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()

    return media, cleaned
```

Porting note:
- Keep this almost verbatim
- In Talos, return a richer contract, e.g. `ExtractedMedia(path, is_voice)`
- Pair it with a file-existence check in delivery.py before adapter dispatch

-------------------------------------------------------------------------------
4. Image and audio caching helpers with retry
-------------------------------------------------------------------------------

Why this matters:
Platform CDN URLs expire. Hermes caches incoming media locally so downstream
components can operate on file paths reliably. Talos should do the same.

Source:
- ~/.hermes/hermes-agent/gateway/platforms/base.py:58-120
- ~/.hermes/hermes-agent/gateway/platforms/base.py:160-222

Suggested Talos destination:
- talos_gateway/media_cache.py
- or vocal_cortex/storage.py for audio-specific utilities

Reference blocks:

```python
def cache_image_from_bytes(data: bytes, ext: str = ".jpg") -> str:
    cache_dir = get_image_cache_dir()
    filename = f"img_{uuid.uuid4().hex[:12]}{ext}"
    filepath = cache_dir / filename
    filepath.write_bytes(data)
    return str(filepath)
```

```python
async def cache_image_from_url(url: str, ext: str = ".jpg", retries: int = 2) -> str:
    import asyncio
    import httpx
    import logging as _logging
    _log = _logging.getLogger(__name__)

    last_exc = None
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for attempt in range(retries + 1):
            try:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; JuliannaAgent/1.0)",
                        "Accept": "image/*,*/*;q=0.8",
                    },
                )
                response.raise_for_status()
                return cache_image_from_bytes(response.content, ext)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 429:
                    raise
                if attempt < retries:
                    wait = 1.5 * (attempt + 1)
                    _log.debug("Media cache retry %d/%d for %s (%.1fs): %s",
                               attempt + 1, retries, url[:80], wait, exc)
                    await asyncio.sleep(wait)
                    continue
                raise
    raise last_exc
```

```python
def cache_audio_from_bytes(data: bytes, ext: str = ".ogg") -> str:
    cache_dir = get_audio_cache_dir()
    filename = f"audio_{uuid.uuid4().hex[:12]}{ext}"
    filepath = cache_dir / filename
    filepath.write_bytes(data)
    return str(filepath)
```

```python
async def cache_audio_from_url(url: str, ext: str = ".ogg", retries: int = 2) -> str:
    import asyncio
    import httpx
    import logging as _logging
    _log = _logging.getLogger(__name__)

    last_exc = None
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for attempt in range(retries + 1):
            try:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; JuliannaAgent/1.0)",
                        "Accept": "audio/*,*/*;q=0.8",
                    },
                )
                response.raise_for_status()
                return cache_audio_from_bytes(response.content, ext)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 429:
                    raise
                if attempt < retries:
                    wait = 1.5 * (attempt + 1)
                    _log.debug("Audio cache retry %d/%d for %s (%.1fs): %s",
                               attempt + 1, retries, url[:80], wait, exc)
                    await asyncio.sleep(wait)
                    continue
                raise
    raise last_exc
```

Porting note:
- Replace `JuliannaAgent/1.0` with a Talos user-agent string
- In Talos, make cache root configurable under `TALOS_GATEWAY` or `VOCAL_CORTEX`
- Add lifecycle cleanup job via TemporalLobe or a management command

-------------------------------------------------------------------------------
5. Document cache with path traversal protection
-------------------------------------------------------------------------------

Why this matters:
If platforms send PDFs or docs, Talos should preserve them as local files.
Hermes includes a good filename sanitization and path confinement check.

Source:
- ~/.hermes/hermes-agent/gateway/platforms/base.py:234-279

Suggested Talos destination:
- talos_gateway/media_cache.py

Reference blocks:

```python
SUPPORTED_DOCUMENT_TYPES = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
```

```python
def cache_document_from_bytes(data: bytes, filename: str) -> str:
    cache_dir = get_document_cache_dir()
    safe_name = Path(filename).name if filename else "document"
    safe_name = safe_name.replace("\x00", "").strip()
    if not safe_name or safe_name in (".", ".."):
        safe_name = "document"
    cached_name = f"doc_{uuid.uuid4().hex[:12]}_{safe_name}"
    filepath = cache_dir / cached_name
    if not filepath.resolve().is_relative_to(cache_dir.resolve()):
        raise ValueError(f"Path traversal rejected: {filename!r}")
    filepath.write_bytes(data)
    return str(filepath)
```

Porting note:
- Keep the path traversal guard exactly
- This is good security hygiene and worth preserving unchanged

-------------------------------------------------------------------------------
6. Normalized inbound/outbound contracts
-------------------------------------------------------------------------------

Why this matters:
Hermes had a reasonable normalized message event structure. Talos already has a
better planned contract model in Layer 4, but this is still useful as a sanity
check for the fields adapters actually need.

Source:
- ~/.hermes/hermes-agent/gateway/platforms/base.py:317-400

Suggested Talos destination:
- talos_gateway/contracts.py (do NOT port as-is; use as a reference)

Reference shape:

```python
@dataclass
class MessageEvent:
    text: str
    message_type: MessageType = MessageType.TEXT
    source: SessionSource = None
    raw_message: Any = None
    message_id: Optional[str] = None
    media_urls: List[str] = field(default_factory=list)
    media_types: List[str] = field(default_factory=list)
    reply_to_message_id: Optional[str] = None
    reply_to_text: Optional[str] = None
    auto_skill: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
```

```python
@dataclass
class SendResult:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    raw_response: Any = None
    retryable: bool = False
```

Porting note:
- Talos should keep its planned Pydantic contracts (`PlatformEnvelope`, `DeliveryPayload`)
- But `SendResult` is still a useful return shape for adapter internals

-------------------------------------------------------------------------------
7. Discord voice-message metadata generation
-------------------------------------------------------------------------------

Why this matters:
This is one of the highest-value Hermes fragments. Discord voice-message uploads
want duration + a waveform payload. That is not obvious, and Hermes already
solved it.

Source:
- ~/.hermes/hermes-agent/tools/send_message_tool.py:290-444

Suggested Talos destination:
- talos_gateway/adapters/discord_utils.py
- or vocal_cortex/discord_voice.py

Reference blocks:

```python
def _ffprobe_duration_seconds(file_path: str) -> Optional[float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run([
            ffprobe,
            "-v", "-loglevel", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ], capture_output=True, text=True, timeout=35, check=False)

        if proc.returncode != 0:
            return None
        return float(proc.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, OSError) as e:
        logger.warning("ffprobe failed to get duration for %s: %s", file_path, e)
        return None
```

```python
def _discord_waveform_bytes(file_path: str, bars: int = 256) -> Optional[bytes]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        proc = subprocess.run([
            ffmpeg,
            "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", file_path,
            "-f", "s16le",
            "-ac", "1",
            "-ar", "16000",
            "-acodec", "pcm_s16le",
            "pipe:1",
        ], capture_output=True, timeout=120, check=False)

        if proc.returncode != 0 or not proc.stdout:
            return None
        pcm = proc.stdout
        n_samples = len(pcm) // 2
        if n_samples == 0:
            return None

        fmt = f"<{n_samples}h"
        samples = struct.unpack(fmt, pcm[: n_samples * 2])

        chunk = max(1, n_samples // bars)
        peaks: list[int] = []
        for i in range(0, n_samples, chunk):
            window = samples[i : i + chunk]
            peaks.append(max(abs(s) for s in window))

        if len(peaks) > bars:
            peaks = peaks[: bars]
        elif len(peaks) < bars:
            peaks.extend([0] * (bars - len(peaks)))

        peak_max = max(peaks) or 1
        return bytes(min(255, int(p * 255 // peak_max)) for p in peaks)
    except (subprocess.TimeoutExpired, OSError, struct.error) as e:
        logger.warning("ffmpeg failed to get waveform for %s: %s", file_path, e)
        return None
```

```python
def discord_voice_metadata(file_path: str) -> Tuple[float, str]:
    duration = _ffprobe_duration_seconds(file_path)
    if duration is None or duration <= 0:
        duration = 1.0

    raw_bytes = _discord_waveform_bytes(file_path)
    if raw_bytes is None:
        waveform_b64 = _STATIC_WAVEFORM_B64
    else:
        waveform_b64 = base64.b64encode(raw_bytes).decode()

    return duration, waveform_b64
```

Porting note:
- This is worth porting almost exactly
- Put `_STATIC_WAVEFORM_B64` beside it in the Talos utility module
- Add tests with a known short audio fixture

-------------------------------------------------------------------------------
8. Telegram MarkdownV2 helpers
-------------------------------------------------------------------------------

Why this matters:
Telegram formatting is brittle. Hermes has simple helpers for escaping and for
stripping formatting in fallback cases.

Source:
- ~/.hermes/hermes-agent/gateway/platforms/telegram.py:77-104

Suggested Talos destination:
- talos_gateway/adapters/telegram_utils.py

Reference blocks:

```python
_MDV2_ESCAPE_RE = re.compile(r'([_*\[\]()~`>#\+\-=|{}.!\\])')


def _escape_mdv2(text: str) -> str:
    return _MDV2_ESCAPE_RE.sub(r'\\\1', text)
```

```python
def _strip_mdv2(text: str) -> str:
    cleaned = re.sub(r'\\([_*\[\]()~`>#\+\-=|{}.!\\])', r'\1', text)
    cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
    cleaned = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', cleaned)
    cleaned = re.sub(r'~([^~]+)~', r'\1', cleaned)
    cleaned = re.sub(r'\|\|([^|]+)\|\|', r'\1', cleaned)
    return cleaned
```

Porting note:
- Keep these as small pure helpers
- Use only inside the Telegram adapter, not in generic delivery code

-------------------------------------------------------------------------------
9. Target parsing for chat/thread/topic addressing
-------------------------------------------------------------------------------

Why this matters:
Cross-platform outbound delivery often needs a compact target syntax, especially
for topic/thread-aware platforms.

Source:
- ~/.hermes/hermes-agent/tools/send_message_tool.py:211-223

Suggested Talos destination:
- talos_gateway/targeting.py

Reference block:

```python
def _parse_target_ref(platform_name: str, target_ref: str):
    if platform_name == "telegram":
        match = _TELEGRAM_TOPIC_TARGET_RE.fullmatch(target_ref)
        if match:
            return match.group(1), match.group(2), True
    if platform_name == "feishu":
        match = _FEISHU_TARGET_RE.fullmatch(target_ref)
        if match:
            return match.group(1), match.group(2), True
    if target_ref.lstrip("-").isdigit():
        return target_ref, None, True
    return None, None, False
```

Porting note:
- Talos should generalize this into a typed parser returning `TargetRef`
- But the regex logic itself is worth preserving

-------------------------------------------------------------------------------
10. Media-only mirror summaries
-------------------------------------------------------------------------------

Why this matters:
If a response contains only attachments and no text, logs/history still need a
human-readable placeholder.

Source:
- ~/.hermes/hermes-agent/tools/send_message_tool.py:226-242

Suggested Talos destination:
- talos_gateway/delivery.py

Reference block:

```python
def _describe_media_for_mirror(media_files):
    if not media_files:
        return ""
    if len(media_files) == 1:
        media_path, is_voice = media_files[0]
        ext = os.path.splitext(media_path)[1].lower()
        if is_voice and ext in _VOICE_EXTS:
            return "[Sent voice message]"
        if ext in _IMAGE_EXTS:
            return "[Sent image attachment]"
        if ext in _VIDEO_EXTS:
            return "[Sent video attachment]"
        if ext in _AUDIO_EXTS:
            return "[Sent audio attachment]"
        return "[Sent document attachment]"
    return f"[Sent {len(media_files)} media attachments]"
```

Porting note:
- Keep the idea, maybe rename to `describe_attachments_for_history()`
- Useful for GatewayDeliveryLog, session history, and debugging

-------------------------------------------------------------------------------
11. Recommended Talos placement map
-------------------------------------------------------------------------------

Recommended placement for ported logic:

- `talos_gateway/base_patterns.py`
  - truncate_message
  - extract_media
  - describe_attachments_for_history

- `talos_gateway/media_cache.py`
  - cache_image_from_bytes
  - cache_image_from_url
  - cache_audio_from_bytes
  - cache_audio_from_url
  - cache_document_from_bytes
  - supported document types
  - cache cleanup helpers

- `talos_gateway/targeting.py`
  - target/thread/topic parsing

- `talos_gateway/adapters/telegram_utils.py`
  - Telegram MarkdownV2 helpers

- `talos_gateway/adapters/discord_utils.py`
  - discord_voice_metadata
  - waveform generation
  - duration probing

-------------------------------------------------------------------------------
12. Porting priorities
-------------------------------------------------------------------------------

Port first:
1. truncate_message
2. extract_media
3. cache_audio_from_url / cache_image_from_url
4. discord_voice_metadata
5. Telegram markdown helpers

Port later if needed:
6. target parsing generalization
7. media-only mirror summaries
8. document cache helpers

Skip entirely:
- Hermes adapter inheritance tree
- Hermes gateway session model
- Hermes config plumbing
- Hermes AIAgent-specific delivery logic

-------------------------------------------------------------------------------
13. Voxtral runtime logic worth preserving
-------------------------------------------------------------------------------

Why this matters:
Hermes's Voxtral integration contains a small but important cluster of logic that
is easy to underestimate:

- binary discovery
- ASR/TTS model path resolution
- tokenizer resolution
- GGUF vs model-directory branching
- WSL -> Windows path conversion
- WAV normalization via ffmpeg
- Windows-writeable output staging for TTS

This is not gateway logic. It is provider runtime logic and should live only in
Talos's `vocal_cortex/providers/` layer.

Recommended Talos destination:
- `vocal_cortex/providers/voxtral_runtime.py`
- `vocal_cortex/providers/stt_voxtral.py`
- `vocal_cortex/providers/tts_voxtral.py`
- `vocal_cortex/providers/host_paths.py`

Source:
- `~/.hermes/hermes-agent/tools/voxtral_tools.py`
- `~/.hermes/hermes-agent/tools/transcription_tools.py`
- `~/.hermes/hermes-agent/tools/tts_tool.py`

### 13.1 Low-level Voxtral runtime helpers

Source:
- `tools/voxtral_tools.py:77-167`

Reference blocks:

```python
def _load_voxtral_config() -> Dict[str, Any]:
    """Read the ``voxtral`` section from config.yaml."""
    try:
        from hermes_cli.config import load_config
        return load_config().get("voxtral", {})
    except Exception:
        return {}
```

```python
def _wsl_to_win(path: str) -> str:
    """Convert a WSL Linux path to a native Windows path via ``wslpath -w``."""
    path = os.path.abspath(os.path.expanduser(path))
    try:
        result = subprocess.run(
            ["wslpath", "-w", path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    if path.startswith("/mnt/c/"):
        return "C:/" + path[len("/mnt/c/"):]
    return path
```

```python
def _resolve_binary(cfg: Dict[str, Any]) -> Optional[str]:
    """Return the Linux-mount path to the voxtral binary, or None."""
    env_bin = os.getenv("VOXTRAL_BINARY", "").strip()
    if env_bin and os.path.isfile(env_bin):
        return env_bin
    cfg_bin = (cfg.get("binary") or "").strip()
    if cfg_bin and os.path.isfile(cfg_bin):
        return cfg_bin
    for candidate in [_VOXTRAL_EXE_LINUX, _VOXTRAL_EXE_WIN]:
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which(_VOXTRAL_EXE_RAW)
    if found:
        return found
    return None
```

```python
def _resolve_model(kind: str, cfg: Dict[str, Any]) -> str:
    """Resolve a model path: env > config > default."""
    use_gguf = (
        os.getenv("VOXTRAL_USE_GGUF", "").strip().lower() in ("1", "true", "yes")
        or cfg.get("use_gguf", True)
    )
    mapping = {
        "asr": {
            "env": "VOXTRAL_ASR_MODEL",
            "cfg_key": "asr_model",
            "cfg_gguf_key": "asr_gguf",
            "default_gguf": _MODELS_ROOT + "/voxtral-q4.gguf",
            "default": _MODELS_ROOT + "/voxtral",
        },
        "tts": {
            "env": "VOXTRAL_TTS_MODEL",
            "cfg_key": "tts_model",
            "cfg_gguf_key": "tts_gguf",
            "default_gguf": _MODELS_ROOT + "/voxtral-tts-q4.gguf",
            "default": _MODELS_ROOT + "/voxtral-tts",
        },
    }
    m = mapping[kind]
    val = os.getenv(m["env"], "").strip()
    if val:
        return val
    gguf_val = (cfg.get(m["cfg_gguf_key"]) or "").strip()
    if use_gguf and gguf_val:
        return gguf_val
    val = (cfg.get(m["cfg_key"]) or "").strip()
    if val:
        return val
    if use_gguf:
        return m["default_gguf"]
    return m["default"]
```

```python
def _resolve_tokenizer(cfg: Dict[str, Any]) -> str:
    env_tok = os.getenv("VOXTRAL_TOKENIZER", "").strip()
    if env_tok:
        return env_tok
    cfg_tok = (cfg.get("tokenizer") or "").strip()
    if cfg_tok:
        return cfg_tok
    return _MODELS_ROOT + "/tekken.json"
```

Porting note:
- Keep the logic, but do not keep Hermes config loading as-is
- In Talos, read from `settings.VOCAL_CORTEX['providers']['voxtral']`
- Move `_wsl_to_win()` into a host-path helper module so the provider does not
  become the global path abstraction for all of Talos

### 13.2 Audio normalization helper for Voxtral ASR

Source:
- `tools/voxtral_tools.py:179-194`

Reference block:

```python
def _convert_to_wav_if_needed(file_path: str) -> Optional[str]:
    """Convert non-WAV audio to WAV for voxtral if ffmpeg is available."""
    if Path(file_path).suffix.lower() == ".wav":
        return file_path
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    out_path = file_path.rsplit(".", 1)[0] + "_voxtral_input.wav"
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", file_path, "-ar", "16000", "-ac", "1", out_path],
            capture_output=True, timeout=60, check=True,
        )
        return out_path
    except Exception:
        return None
```

Porting note:
- Keep this exact preprocessing behavior inside `stt_voxtral.py`
- Do not generalize it into the gateway core; this is provider-specific

### 13.3 Voxtral ASR subprocess wrapper

Source:
- `tools/voxtral_tools.py:198-271`

Reference block:

```python
def voxtral_transcribe(
    audio_path: str,
    *,
    binary: Optional[str] = None,
    model: Optional[str] = None,
    tokenizer: Optional[str] = None,
    delay: Optional[int] = None,
    max_mel_frames: Optional[int] = None,
) -> Dict[str, Any]:
    cfg = _load_voxtral_config()
    bin_path = binary or _resolve_binary(cfg)
    if not bin_path:
        return {
            "success": False,
            "transcript": "",
            "error": "Voxtral binary not found.",
        }

    audio = Path(audio_path).expanduser()
    if not audio.exists():
        converted = _convert_to_wav_if_needed(str(audio))
        if converted is None:
            return {
                "success": False,
                "transcript": "",
                "error": f"Audio file not found or unsupported format: {audio_path}",
            }
        audio = Path(converted)

    model_path = model or _resolve_model("asr", cfg)
    tok_path = tokenizer or _resolve_tokenizer(cfg)
    is_gguf = model_path.endswith(".gguf")

    w_model = _wsl_to_win(model_path)
    w_tok = _wsl_to_win(tok_path)
    w_audio = _wsl_to_win(str(audio))

    cmd = [bin_path, "transcribe", "--audio", w_audio]
    if is_gguf:
        cmd += ["--gguf", w_model]
    else:
        cmd += ["--model", w_model]
    cmd += ["--tokenizer", w_tok]
    cmd += [
        "--delay", str(delay if delay is not None else _lookup_int(cfg, "asr_delay", DEFAULT_DELAY)),
        "--max-mel-frames", str(max_mel_frames if max_mel_frames is not None else _lookup_int(cfg, "asr_max_mel_frames", DEFAULT_MAX_MEL_FRAMES)),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            stderr_snip = (result.stderr or "")[-500:]
            return {"success": False, "transcript": "", "error": f"voxtral transcribe failed: {stderr_snip}"}

        transcript = result.stdout.strip()
        return {"success": True, "transcript": transcript, "provider": "voxtral"}

    except subprocess.TimeoutExpired:
        return {"success": False, "transcript": "", "error": "voxtral ASR timed out (>300s)"}
    except Exception as exc:
        return {"success": False, "transcript": "", "error": f"voxtral ASR failed: {exc}"}
```

Porting note:
- In Talos, this should return a typed `TranscriptionResult`, not a raw dict
- Keep subprocess invocation and GGUF switching, but move parameter defaults to
  `VOCAL_CORTEX` settings

### 13.4 Voxtral TTS subprocess wrapper

Source:
- `tools/voxtral_tools.py:275-380`

Reference block:

```python
def voxtral_speak(
    text: str,
    output_path: str,
    *,
    binary: Optional[str] = None,
    model: Optional[str] = None,
    tokenizer: Optional[str] = None,
    voice: Optional[str] = None,
    max_frames: Optional[int] = None,
    euler_steps: Optional[int] = None,
) -> Dict[str, Any]:
    if not text or not text.strip():
        return {"success": False, "file_path": "", "error": "Text is required"}

    cfg = _load_voxtral_config()
    bin_path = binary or _resolve_binary(cfg)
    if not bin_path:
        return {"success": False, "file_path": "", "error": "Voxtral binary not found."}

    model_path = model or _resolve_model("tts", cfg)
    tok_path = tokenizer or _resolve_tokenizer(cfg)
    voice_name = voice or cfg.get("default_voice", DEFAULT_VOICE)
    is_gguf = model_path.endswith(".gguf")

    voices_dir = None
    if is_gguf:
        vcfg = cfg.get("voices_dir", "")
        if vcfg:
            voices_dir = vcfg
        else:
            candidates = [_MODELS_ROOT + "/voxtral-tts/voice_embedding"]
            for c in candidates:
                if Path(c).is_dir():
                    voices_dir = c
                    break
        if not voices_dir:
            voices_dir = _MODELS_ROOT + "/voxtral-tts/voice_embedding"

    w_model = _wsl_to_win(model_path)
    w_tok = _wsl_to_win(tok_path)
    w_out = _wsl_to_win(str(output_path))

    cmd = [
        bin_path, "speak",
        "--text", text,
        "--voice", voice_name,
        "--output", w_out,
        "--tokenizer", w_tok,
        "--max-frames", str(max_frames if max_frames is not None else _lookup_int(cfg, "tts_max_frames", DEFAULT_MAX_FRAMES)),
        "--euler-steps", str(euler_steps if euler_steps is not None else _lookup_int(cfg, "tts_euler_steps", DEFAULT_EULER_STEPS)),
    ]

    if is_gguf:
        cmd += ["--gguf", w_model]
        w_vd = _wsl_to_win(voices_dir)
        cmd += ["--voices-dir", w_vd]
    else:
        cmd += ["--model", w_model]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            stderr_snip = (result.stderr or "")[-500:]
            return {"success": False, "file_path": "", "error": f"voxtral speak failed: {stderr_snip}"}

        if Path(output_path).exists() and os.path.getsize(output_path) > 0:
            return {"success": True, "file_path": str(output_path), "provider": "voxtral-tts"}

        return {
            "success": False,
            "file_path": "",
            "error": f"voxtral TTS completed but output file missing: {output_path}",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "file_path": "", "error": "voxtral TTS timed out (>300s)"}
    except Exception as exc:
        return {"success": False, "file_path": "", "error": f"voxtral TTS failed: {exc}"}
```

Porting note:
- Keep the runtime mechanics, but return a typed `SynthesisResult`
- Split voices-dir resolution into a small helper in `voxtral_runtime.py`

### 13.5 Hermes STT provider routing that calls Voxtral

Source:
- `tools/transcription_tools.py:507-532`
- `tools/transcription_tools.py:572-629`

Reference blocks:

```python
def _transcribe_voxtral(file_path: str, _model_name: str) -> Dict[str, Any]:
    try:
        from tools.voxtral_tools import voxtral_transcribe
    except ImportError:
        return {
            "success": False,
            "transcript": "",
            "error": "voxtral_tools module not available",
        }

    result = voxtral_transcribe(file_path)
    if result.get("success"):
        logger.info(
            "Transcribed %s via Voxtral ASR (%d chars)",
            Path(file_path).name,
            len(result.get("transcript", "")),
        )
    else:
        logger.error("Voxtral ASR failed: %s", result.get("error"))

    return result
```

```python
def transcribe_audio(file_path: str, model: Optional[str] = None) -> Dict[str, Any]:
    error = _validate_audio_file(file_path)
    if error:
        return error

    stt_config = _load_stt_config()
    if not is_stt_enabled(stt_config):
        return {
            "success": False,
            "transcript": "",
            "error": "STT is disabled in config.yaml (stt.enabled: false).",
        }

    provider = _get_provider(stt_config)

    if provider == "voxtral":
        return _transcribe_voxtral(file_path, model or "voxtral-4b-rq-realtime")

    if provider == "local":
        ...
```

Porting note:
- Keep the routing idea, not the exact file
- In Talos, this belongs in `vocal_cortex/stt.py` as provider dispatch, with
  a typed result contract and explicit `auto` fallback policy

### 13.6 Hermes TTS provider routing that calls Voxtral-TTS

Source:
- `tools/tts_tool.py:274-336`
- `tools/tts_tool.py:499-576`

Reference blocks:

```python
def _generate_voxtral_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    try:
        from tools.voxtral_tools import voxtral_speak
    except ImportError:
        raise RuntimeError(
            "voxtral_tools module not importable. "
            "Ensure tools/voxtral_tools.py exists and is on sys.path."
        )

    vt_config = tts_config.get("voxtral-tts", {})
    voice = vt_config.get("voice", "casual_female")
    max_frames = vt_config.get("max_frames", 2000)
    euler_steps = vt_config.get("euler_steps", 6)

    on_mnt_c = str(output_path).startswith("/mnt/c/")
    tmp_wav_on_c = "/mnt/c/Users/scfre/voxtral_tts_output.wav"
    gen_path = tmp_wav_on_c

    result = voxtral_speak(
        text, gen_path,
        voice=voice, max_frames=max_frames, euler_steps=euler_steps,
    )
    if not result.get("success"):
        raise RuntimeError(result.get("error", "Voxtral TTS returned unknown failure"))

    if not on_mnt_c or os.path.abspath(gen_path) != os.path.abspath(output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.copy2(gen_path, output_path)

    ext = Path(output_path).suffix.lower()
    if ext not in (".wav",):
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            wav_copy = str(Path(output_path).with_suffix(".wav"))
            shutil.copy2(output_path, wav_copy)
            os.remove(output_path)
            subprocess.run(
                [ffmpeg, "-y", "-i", wav_copy, "-loglevel", "error", output_path],
                check=True, timeout=60,
            )
            if os.path.exists(wav_copy):
                os.remove(wav_copy)
        elif ext != ".wav":
            os.rename(output_path, str(Path(output_path).with_suffix(".wav")))

    return output_path
```

```python
elif provider == "voxtral-tts":
    logger.info("Generating speech with Voxtral TTS (local)...")
    _generate_voxtral_tts(text, file_str, tts_config)

...

if provider in ("edge", "neutts", "voxtral-tts") and not file_str.endswith(".ogg"):
    opus_path = _convert_to_opus(file_str)
    if opus_path:
        file_str = opus_path
        voice_compatible = True
```

Porting note:
- Do not keep the hardcoded `"/mnt/c/Users/scfre/..."` staging path in Talos
- Replace it with a configurable staging root in `VOCAL_CORTEX`
- Keep the format-conversion pattern, but isolate it inside the Voxtral provider

### 13.7 Talos design guidance for these runtime blocks

Recommended Talos split:

- `vocal_cortex/providers/host_paths.py`
  - WSL/Windows conversion
  - provider-specific writable temp path selection

- `vocal_cortex/providers/voxtral_runtime.py`
  - binary/model/tokenizer/voices-dir resolution
  - subprocess command construction
  - timeout handling

- `vocal_cortex/providers/stt_voxtral.py`
  - audio preprocessing
  - ASR invocation
  - typed `TranscriptionResult`

- `vocal_cortex/providers/tts_voxtral.py`
  - staging + synthesis + format conversion
  - typed `SynthesisResult`

The important architectural line:
- provider plugin = public unit
- runtime helper = private implementation detail for that provider family

-------------------------------------------------------------------------------
14. Final recommendation
-------------------------------------------------------------------------------

If Talos builds Layer 4 correctly, these Hermes fragments become:
- small utility modules,
- heavily tested,
- called by new Talos-native adapters,
- and completely decoupled from Hermes runtime architecture.

That is the right balance: preserve the hard-won platform details, discard the
old transport brain.
