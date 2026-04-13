"""Identity addon: compact markdown table of available skills.

Primary source: SkillEngram records linked via identity_disc FK.
Fallback: skill-tagged Engrams intersecting enabled ToolDefinitions (backward compat).
"""

import logging
from typing import Any, Dict, List, Optional

from frontal_lobe.models import ReasoningTurn
from hippocampus.models import Engram, SkillEngram

logger = logging.getLogger(__name__)

SKILL_TAG = 'skill'
MAX_SKILLS_BLOCK_CHARS = 2000
MAX_DESC_CELL_CHARS = 320


def _truncate_cell(text: str, max_len: int) -> str:
    one = (text or '').replace('\n', ' ').strip()
    if len(one) <= max_len:
        return one
    if max_len <= 3:
        return one[:max_len]
    return one[: max_len - 3] + '...'


def _build_table(rows: List[tuple[str, str]]) -> str:
    header = (
        '## Available Skills\n\n'
        '| Skill | Description |\n'
        '|-------|-------------|\n'
    )
    body_lines = [f'| {name} | {desc} |' for name, desc in rows]
    return header + '\n'.join(body_lines)


def _fit_rows_with_cap(
    rows: List[tuple[str, str]], max_chars: int
) -> tuple[str, int]:
    """Return rendered table (with optional overflow notice) and omitted row count."""
    if not rows:
        return '', 0

    for take in range(len(rows), 0, -1):
        chunk = rows[:take]
        omitted = len(rows) - take
        footer = f'\n\n...and {omitted} more' if omitted else ''
        candidate = _build_table(chunk) + footer
        if len(candidate) <= max_chars:
            return candidate, omitted

    footer_only = f'## Available Skills\n\n...and {len(rows)} more'
    if len(footer_only) <= max_chars:
        return footer_only, len(rows)

    first_name, first_desc = rows[0]
    tight = ''
    for cap in (200, 80, 40, 20):
        tight = _build_table([(first_name, _truncate_cell(first_desc, cap))])
        if len(tight) <= max_chars:
            return tight, len(rows) - 1
    return tight[:max_chars], len(rows) - 1


def _rows_from_skill_engrams(
    identity_disc: 'IdentityDisc',
) -> Optional[List[tuple[str, str]]]:
    """Primary path: SkillEngram records linked via identity_disc FK."""
    skills = (
        SkillEngram.objects.filter(
            identity_disc=identity_disc,
            is_active=True,
        )
        .order_by('name')
    )
    if not skills.exists():
        return None

    rows: List[tuple[str, str]] = []
    for skill in skills:
        desc = _truncate_cell(skill.description, MAX_DESC_CELL_CHARS)
        rows.append((skill.name, desc))
    return rows


def _rows_from_tagged_engrams(
    identity_disc: 'IdentityDisc',
) -> List[tuple[str, str]]:
    """Fallback path: skill-tagged Engrams matching enabled ToolDefinitions."""
    enabled_tools = list(
        identity_disc.enabled_tools.all().order_by('name')
    )
    if not enabled_tools:
        return []

    allowed_lower = {t.name.lower() for t in enabled_tools}

    try:
        base = (
            Engram.objects.filter(
                identity_discs=identity_disc,
                is_active=True,
                tags__name=SKILL_TAG,
            )
            .distinct()
            .order_by('name')
        )
        candidates = [e for e in base if e.name.lower() in allowed_lower]
    except Exception as exc:
        logger.warning(
            '[skills_index_addon] Failed to query tagged engrams: %s', exc
        )
        return []

    rows: List[tuple[str, str]] = []
    for engram in candidates:
        desc = _truncate_cell(engram.description or '', MAX_DESC_CELL_CHARS)
        rows.append((engram.name, desc))
    return rows


def skills_index_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: CONTEXT).

    Lists available skills for the identity disc. Prefers SkillEngram records
    (linked via identity_disc FK). Falls back to skill-tagged Engrams matching
    enabled ToolDefinitions for backward compatibility.
    """
    if not turn or not turn.session:
        return []

    identity_disc = turn.session.identity_disc
    if not identity_disc:
        return []

    rows = _rows_from_skill_engrams(identity_disc)
    if rows is None:
        rows = _rows_from_tagged_engrams(identity_disc)

    if not rows:
        return []

    text, _omitted = _fit_rows_with_cap(rows, MAX_SKILLS_BLOCK_CHARS)
    if not text:
        return []

    return [{'role': 'system', 'content': text}]
