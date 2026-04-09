"""Identity addon: formatted snapshot of IdentityDisc-linked active memory engrams."""

import logging
from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn

logger = logging.getLogger(__name__)

USER_PROFILE_TAG = 'user_profile'
AGENT_MEMORY_TAG = 'agent_memory'
MAX_MEMORY_BLOCK_CHARS = 1500


def _engram_bullet_text(engram) -> str:
    raw = (engram.description or '').strip()
    if not raw:
        raw = (engram.name or '').strip()
    return raw


def _format_snapshot(user_lines: List[str], agent_lines: List[str]) -> str:
    lines: List[str] = ['## Active Memory', '']
    if user_lines:
        lines.extend(['### User Profile', ''])
        for item in user_lines:
            lines.append(f'- {item}')
        lines.append('')
    if agent_lines:
        lines.extend(['### Agent Notes', ''])
        for item in agent_lines:
            lines.append(f'- {item}')
    return '\n'.join(lines).rstrip()


def _truncate_block(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + '...'


def memory_snapshot_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: CONTEXT).

    Builds a markdown block from ``IdentityDisc.memories`` engrams that carry
    ``user_profile`` and/or ``agent_memory`` tags. Engrams with neither tag are
    omitted. Inactive engrams are excluded.
    """
    if not turn or not turn.session:
        return []

    identity_disc = turn.session.identity_disc
    if not identity_disc:
        return []

    try:
        engrams = list(
            identity_disc.memories.filter(is_active=True)
            .prefetch_related('tags')
            .order_by('-modified')
        )
    except Exception as exc:
        logger.warning(
            '[memory_snapshot_addon] Failed to query memories: %s', exc
        )
        return []

    user_lines: List[str] = []
    agent_lines: List[str] = []

    for engram in engrams:
        tag_names = {t.name for t in engram.tags.all()}
        has_user = USER_PROFILE_TAG in tag_names
        has_agent = AGENT_MEMORY_TAG in tag_names
        if not has_user and not has_agent:
            continue
        bullet = _engram_bullet_text(engram)
        if not bullet:
            continue
        if has_user:
            user_lines.append(bullet)
        if has_agent:
            agent_lines.append(bullet)

    if not user_lines and not agent_lines:
        return []

    block = _format_snapshot(user_lines, agent_lines)
    block = _truncate_block(block, MAX_MEMORY_BLOCK_CHARS)
    return [{'role': 'system', 'content': block}]
