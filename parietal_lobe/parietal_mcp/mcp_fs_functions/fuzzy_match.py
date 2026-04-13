"""
Hermes-style fuzzy matching for string patches. Strategies 1–9 in order.
"""
import difflib
import logging
import re
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

STRATEGY_EXACT = 1
STRATEGY_TRIM = 2
STRATEGY_DEDENT = 3
STRATEGY_EXPAND_NL = 4
STRATEGY_EXPAND_TAB = 5
STRATEGY_CRLF = 6
STRATEGY_TRAILING_NL = 7
STRATEGY_REGEX = 8
STRATEGY_DIFFLIB = 9


def _try_find(haystack: str, needle: str) -> Optional[Tuple[int, int]]:
    pos = haystack.find(needle)
    if pos < 0:
        return None
    return pos, pos + len(needle)


def _match_dedent_lines(
    haystack: str,
    needle: str,
) -> Optional[Tuple[int, int]]:
    """Match block where each line matches after lstrip()."""
    hay_parts = haystack.splitlines(True)
    need_parts = needle.splitlines(True)
    if not need_parts:
        return None

    def norm_block(parts: List[str]) -> Tuple[str, ...]:
        return tuple(line.lstrip() for line in parts)

    nd = norm_block(need_parts)
    n_need = len(need_parts)
    for i in range(len(hay_parts) - n_need + 1):
        window = hay_parts[i : i + n_need]
        if norm_block(window) == nd:
            start = sum(len(hay_parts[j]) for j in range(i))
            end = start + sum(len(hay_parts[i + k]) for k in range(n_need))
            return start, end
    return None


def _match_trailing_newline(
    haystack: str,
    needle: str,
) -> Optional[Tuple[int, int]]:
    for variant in (needle, needle.rstrip('\n')):
        span = _try_find(haystack, variant)
        if span is not None:
            return span
    if needle.endswith('\n'):
        span = _try_find(haystack, needle[:-1])
        if span is not None:
            return span
    return None


def _match_regex(
    haystack: str,
    pattern: str,
) -> Optional[Tuple[int, int]]:
    try:
        re_exp = re.compile(pattern, re.DOTALL)
    except re.error:
        return None
    match = re_exp.search(haystack)
    if match is None:
        return None
    return match.start(), match.end()


def _match_difflib_line(
    haystack: str,
    needle: str,
) -> Optional[Tuple[int, int]]:
    hay_lines = haystack.splitlines()
    need_lines = needle.splitlines()
    if not need_lines:
        return None

    best_ratio = 0.0
    best_start = -1
    best_end = -1

    n_need = len(need_lines)
    n_hay = len(hay_lines)
    if n_need > n_hay:
        return None

    for i in range(n_hay - n_need + 1):
        block = '\n'.join(hay_lines[i : i + n_need])
        ratio = difflib.SequenceMatcher(
            None,
            block,
            needle,
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i
            best_end = i + n_need

    if best_ratio < 0.65:
        return None

    hay_parts = haystack.splitlines(True)
    if not hay_parts:
        return None

    line_starts = []
    pos = 0
    for part in hay_parts:
        line_starts.append(pos)
        pos += len(part)

    if best_start >= len(line_starts):
        return None

    start_char = line_starts[best_start]
    end_line_idx = min(best_end - 1, len(hay_parts) - 1)
    end_char = line_starts[end_line_idx] + len(hay_parts[end_line_idx])
    return start_char, end_char


def find_match_span(
    file_content: str,
    old_string: str,
) -> Optional[Tuple[str, int, int, int]]:
    """
    Find old_string in file_content using strategies 1–9 in order.

    Returns:
        (buffer, start, end, strategy_number). `buffer` is the string to slice.
    """
    attempts: List[Tuple[int, Callable[[], Optional[Tuple[str, int, int]]]]] = [
        (
            STRATEGY_EXACT,
            lambda: _span_with_buffer(file_content, _try_find(file_content, old_string)),
        ),
        (
            STRATEGY_TRIM,
            lambda: _span_with_buffer(
                file_content,
                _try_find(file_content, old_string.strip()),
            ),
        ),
        (
            STRATEGY_DEDENT,
            lambda: _span_with_buffer(
                file_content,
                _match_dedent_lines(file_content, old_string),
            ),
        ),
        (
            STRATEGY_EXPAND_NL,
            lambda: _span_with_buffer(
                file_content,
                _try_find(
                    file_content,
                    old_string.replace('\\n', '\n'),
                ),
            ),
        ),
        (
            STRATEGY_EXPAND_TAB,
            lambda: _span_with_buffer(
                file_content,
                _try_find(
                    file_content,
                    old_string.replace('\\t', '\t'),
                ),
            ),
        ),
        (
            STRATEGY_CRLF,
            lambda: _crlf_span(file_content, old_string),
        ),
        (
            STRATEGY_TRAILING_NL,
            lambda: _span_with_buffer(
                file_content,
                _match_trailing_newline(file_content, old_string),
            ),
        ),
        (
            STRATEGY_REGEX,
            lambda: _span_with_buffer(
                file_content,
                _match_regex(file_content, old_string),
            ),
        ),
        (
            STRATEGY_DIFFLIB,
            lambda: _span_with_buffer(
                file_content,
                _match_difflib_line(file_content, old_string),
            ),
        ),
    ]

    for strategy_id, fn in attempts:
        result = fn()
        if result is not None:
            buf, start, end = result
            logger.info(
                '[fuzzy_match] Matched using strategy %s.',
                strategy_id,
            )
            return buf, start, end, strategy_id

    return None


def _span_with_buffer(
    buf: str,
    span: Optional[Tuple[int, int]],
) -> Optional[Tuple[str, int, int]]:
    if span is None:
        return None
    start, end = span
    return buf, start, end


def _crlf_span(
    file_content: str,
    old_string: str,
) -> Optional[Tuple[str, int, int]]:
    h = file_content.replace('\r\n', '\n')
    o = old_string.replace('\r\n', '\n')
    span = _try_find(h, o)
    return _span_with_buffer(h, span)


def apply_replacement(
    file_content: str,
    old_string: str,
    new_string: str,
    replace_all: bool,
) -> Tuple[str, int]:
    """Apply first or all replacements; returns (new_content, strategy_used)."""
    if replace_all:
        return _replace_all(file_content, old_string, new_string)

    span = find_match_span(file_content, old_string)
    if span is None:
        raise ValueError(
            'No fuzzy match found for old_string after trying all strategies.',
        )
    buf, start, end, strategy_id = span
    new_content = buf[:start] + new_string + buf[end:]
    return new_content, strategy_id


def _replace_all(
    file_content: str,
    old_string: str,
    new_string: str,
) -> Tuple[str, int]:
    """Replace every non-overlapping occurrence."""
    content = file_content
    total = 0
    last_strategy = STRATEGY_EXACT

    while True:
        span = find_match_span(content, old_string)
        if span is None:
            break
        buf, start, end, strategy_id = span
        last_strategy = strategy_id
        content = buf[:start] + new_string + buf[end:]
        total += 1
        if total > 10000:
            raise ValueError('replace_all exceeded safety limit.')

    if total == 0:
        raise ValueError(
            'No fuzzy match found for old_string after trying all strategies.',
        )

    logger.info(
        '[fuzzy_match] replace_all applied %s replacement(s); last strategy %s.',
        total,
        last_strategy,
    )
    return content, last_strategy
