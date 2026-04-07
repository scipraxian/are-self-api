"""Shared adapter utilities for I/O media payloads(chunking, conventions)."""

from typing import Iterable, Optional

from talos_gateway.contracts import DeliveryPayload


class ChunkedMessage(list):
    """Placeholder to represent chunked messages with richer metadata."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.chunk_count = len(self)
        self.chunk_size = sum(len(chunk.content) for chunk in self)


def chunk_text(text: str, max_length: int) -> list[str]:
    """Split ``text`` into segments no longer than ``max_length`` characters.

    Args:
        text: Full message body.
        max_length: Maximum characters per chunk; must be positive.

    Returns:
        Non-overlapping chunks; empty input yields an empty list.

    Raises:
        ValueError: If ``max_length`` is not positive.
    """
    if max_length <= 0:
        raise ValueError('max_length must be positive')
    if not text:
        return []
    chunks: list[str] = []
    offset = 0
    total = len(text)
    while offset < total:
        chunks.append(text[offset : offset + max_length])
        offset += max_length
    return chunks


def iter_chunked_payloads(
    payload: DeliveryPayload,
    max_length: int,
) -> Iterable[DeliveryPayload]:
    """Yield DeliveryPayload instances, one per content chunk."""
    parts = chunk_text(payload.content, max_length)
    if not parts:
        yield DeliveryPayload(
            platform=payload.platform,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            content='',
            media_paths=list(payload.media_paths),
            voice_audio_path=payload.voice_audio_path,
            reply_to=payload.reply_to,
            is_voice=payload.is_voice,
        )
        return
    last = len(parts) - 1
    for index, part in enumerate(parts):
        yield DeliveryPayload(
            platform=payload.platform,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            content=part,
            media_paths=list(payload.media_paths) if index == 0 else [],
            voice_audio_path=payload.voice_audio_path
            if index == last
            else None,
            reply_to=payload.reply_to if index == 0 else None,
            is_voice=payload.is_voice and index == last,
        )


def is_likely_audio_mime(content_type: str) -> bool:
    """Return True if content_type looks like audio."""
    lower = content_type.lower()
    return lower.startswith('audio/') or 'ogg' in lower or 'opus' in lower


def truncate_message(
    content: str,
    chunk_indicator_reserve: Optional[int] = 10,
    max_length: int = 4096,
) -> list[str]:
    """Split Markdown-style content into chunks within ``max_length``.

    Respects fenced code blocks so chunks do not split mid-fence when possible.

    Args:
        content: Full message body.
        chunk_indicator_reserve: Space reserved for suffixes such as ``(2/5)``.
            If ``None`` is passed explicitly, treated as ``0``.
        max_length: Maximum characters per chunk.

    Returns:
        One or more string chunks; multiple chunks get ``(i/n)`` suffixes.
    """
    if len(content) <= max_length:
        return [content]

    reserve = (
        chunk_indicator_reserve if chunk_indicator_reserve is not None else 0
    )
    chunk_fence_close = '\n```'

    chunks: list[str] = []
    remaining = content
    carry_lang: Optional[str] = None

    while remaining:
        prefix = f'```{carry_lang}\n' if carry_lang is not None else ''

        headroom = max_length - reserve - len(prefix) - len(chunk_fence_close)
        if headroom < 1:
            headroom = max_length // 2

        if len(prefix) + len(remaining) <= max_length - reserve:
            chunks.append(prefix + remaining)
            break

        region = remaining[:headroom]
        split_at = region.rfind('\n')
        if split_at < headroom // 2:
            split_at = region.rfind(' ')
        if split_at < 1:
            split_at = headroom

        candidate = remaining[:split_at]
        backtick_count = candidate.count('`') - candidate.count('\\`')
        if backtick_count % 2 == 1:
            last_bt = candidate.rfind('`')
            while last_bt > 0 and candidate[last_bt - 1] == '\\':
                last_bt = candidate.rfind('`', 0, last_bt)
            if last_bt > 0:
                safe_split = candidate.rfind(' ', 0, last_bt)
                nl_split = candidate.rfind('\n', 0, last_bt)
                safe_split = max(safe_split, nl_split)
                if safe_split > headroom // 4:
                    split_at = safe_split

        chunk_body = remaining[:split_at]
        remaining = remaining[split_at:].lstrip()
        full_chunk = prefix + chunk_body

        in_code = carry_lang is not None
        lang = carry_lang or ''
        for line in chunk_body.split('\n'):
            stripped = line.strip()
            if stripped.startswith('```'):
                if in_code:
                    in_code = False
                    lang = ''
                else:
                    in_code = True
                    tag = stripped[3:].strip()
                    lang = tag.split()[0] if tag else ''

        if in_code:
            full_chunk += chunk_fence_close
            carry_lang = lang
        else:
            carry_lang = None

        chunks.append(full_chunk)

    if len(chunks) > 1:
        total = len(chunks)
        chunks = [
            '%s (%s/%s)' % (chunk, i + 1, total)
            for i, chunk in enumerate(chunks)
        ]

    return chunks
