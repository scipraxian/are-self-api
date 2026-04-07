"""Shared adapter utilities for I/O media payloads(chunking, conventions)."""

from typing import Iterable, List, Optional

from talos_gateway.contracts import DeliveryPayload

class ChunkedMessage(list):
    """Placeholder to represent chunked messages with richer metadata"""
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.chunk_count = len(self)
        self.chunk_size = sum(
            len(chunk.content) for chunk in self
        )

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
    payload: DeliveryPayload, max_length: int
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
            voice_audio_path=payload.voice_audio_path if index == last else None,
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
        max_length: int = 4096) -> List[str]:
    """Cleans and reformats .md styled messages for different platforms and outputs them into chunks for better LLM
    parsing.
    """
    if len(content) <= max_length:
        return [content]

    # Extra room for suffixes like (2/5) from an LLM
    CHUNK_INDICATOR_RESERVE = chunk_indicator_reserve if not None else 0
    # Closes a chunk <= 4096 that is Marked-down styled code
    # until next chunk begins with ```lang
    CHUNK_FENCE_CLOSE = "\n```"

    chunks: List[str] = []
    remaining = content
    # Language used in the last chunk that started a fence
    carry_lang: Optional[str] = None

    while remaining:
        # Continuation of the fenced block started by the last chunk
        # in the message
        prefix = f"```{carry_lang}\n" if carry_lang is not None else ""

        # How many characters to fit into each chunk with arbitrary fallback if < 1
        headroom = max_length - CHUNK_INDICATOR_RESERVE - len(prefix) - len(CHUNK_FENCE_CLOSE)
        if headroom < 1:
            headroom = max_length // 2

        #
        if len(prefix) + len(remaining) <= max_length - CHUNK_INDICATOR_RESERVE:
            chunks.append(prefix + remaining)
            break

        # Characters pass opened chunk fence
        region = remaining[:headroom]
        # Find best end-point for cleaner output
        split_at = region.rfind("\n")
        if split_at < headroom // 2:
            split_at = region.rfind(" ")
        if split_at < 1:
            split_at = headroom

        # Check for any other characters in inlined code
        # or a malformed fence block indicated by odd # of backticks
        candidate = remaining[:split_at]
        backtick_count = candidate.count("`") - candidate.count("\\`")
        if backtick_count % 2 == 1:
            last_bt = candidate.rfind("`")
            while last_bt > 0 and candidate[last_bt - 1] == "\\":
                last_bt = candidate.rfind("`", 0, last_bt)
            # Look through each backtick to find one near the closes
            # safe character to separate with new splitting point
            if last_bt > 0:
                safe_split = candidate.rfind(" ", 0, last_bt)
                nl_split = candidate.rfind("\n", 0, last_bt)
                safe_split = max(safe_split, nl_split)
                if safe_split > headroom // 4:
                    split_at = safe_split

        chunk_body = remaining[:split_at]
        remaining = remaining[split_at:].lstrip()
        full_chunk = prefix + chunk_body

        # If in code within chunk, parse current lang
        # closes internal code block and sets its lang for next chunk
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
            full_chunk += CHUNK_FENCE_CLOSE
            carry_lang = lang
        else:
            carry_lang = None

        chunks.append(full_chunk)

    if len(chunks) > 1:
        total = len(chunks)
        chunks = [f"{chunk} ({i + 1}/{total})" for i, chunk in enumerate(chunks)]

    return chunks