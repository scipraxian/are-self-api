"""Identity addon: encourage tool use for models that under-invoke tools."""

from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn

MAX_TOOL_GUIDANCE_CHARS = 1000

# Substrings matched against ``provider_unique_model_id`` (lowercased).
WEAK_TOOL_USERS = frozenset(
    (
        'gpt-4',
        'gpt-4o-mini',
        'codex',
        'claude-sonnet-3.5',
    )
)


def _is_weak_tool_model(provider_unique_model_id: str) -> bool:
    lowered = (provider_unique_model_id or '').lower()
    if not lowered:
        return False
    for needle in WEAK_TOOL_USERS:
        if needle in lowered:
            return True
    return False


def _truncate_block(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + '...'


def _format_guidance(tools: List) -> str:
    lines = [
        '## Available Tools',
        (
            'You have access to the following tools. Prefer them over guessing '
            'when you need side effects or fresh data:'
        ),
        '',
    ]
    for tool in tools:
        desc = (tool.description or '').replace('\n', ' ').strip()
        if len(desc) > 200:
            desc = desc[:197] + '...'
        lines.append(f'- **{tool.name}** — {desc}')
    lines.extend(
        [
            '',
            'When you need to accomplish something, prefer using a tool over '
            'guessing.',
            'After each action, verify the result before continuing.',
        ]
    )
    return '\n'.join(lines)


def tool_guidance_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: TERMINAL).

    Uses the *previous* turn's model (``last_turn.model_usage_record``) to decide
    whether to inject tool guidance. Turn 1 has no prior model and returns [].
    """
    if not turn or not turn.session:
        return []

    identity_disc = turn.session.identity_disc
    if not identity_disc:
        return []

    if not turn.last_turn:
        return []

    usage = turn.last_turn.model_usage_record
    if not usage or not usage.ai_model_provider:
        return []

    provider_id = usage.ai_model_provider.provider_unique_model_id
    if not _is_weak_tool_model(provider_id):
        return []

    tools = list(identity_disc.enabled_tools.all().order_by('name'))
    if not tools:
        return []

    body = _format_guidance(tools)
    body = _truncate_block(body, MAX_TOOL_GUIDANCE_CHARS)
    return [{'role': 'system', 'content': body}]
