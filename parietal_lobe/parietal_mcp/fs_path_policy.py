"""
Shared filesystem path policy for MCP tools and personal_agent_tools shim.

Write paths must be relative and stay under Django BASE_DIR when not absolute.
"""
import os
from typing import Optional

from django.conf import settings

BLOCKED_PATH_SEGMENTS = frozenset(
    {
        'venv',
        '__pycache__',
        '.git',
        'node_modules',
        'site-packages',
    }
)


def get_base_dir() -> str:
    """Return normalized project root path."""
    return os.path.normpath(str(settings.BASE_DIR))


def validate_blocked_segments(path: str) -> Optional[str]:
    """Returns an error string if the path crosses blocked dirs, else None."""
    if not path:
        return 'Error: path is required.'

    normalized = os.path.normpath(path).replace('\\', '/')
    segments = normalized.split('/')

    for segment in segments:
        if segment in BLOCKED_PATH_SEGMENTS:
            return (
                f'Error: Access denied. Path contains '
                f"blocked segment '{segment}'."
            )

    return None


def validate_write_path_under_base(path: str) -> Optional[str]:
    """
    Enforces writes to relative paths under BASE_DIR (no traversal).

    Absolute paths are rejected for writes.
    """
    blocked = validate_blocked_segments(path)
    if blocked:
        return blocked

    if os.path.isabs(path):
        return (
            'Error: Write access denied. Use a path relative to the project root.'
        )

    base_dir = get_base_dir()
    full_path = os.path.normpath(os.path.join(base_dir, path))

    try:
        common = os.path.commonpath([base_dir, full_path])
        if common.lower() != base_dir.lower():
            return (
                'Error: Write access denied. '
                'Target is outside the project root.'
            )
    except ValueError:
        return 'Error: Write access denied. Drive mismatch.'

    return None


def resolve_write_path(path: str) -> str:
    """Join relative path to BASE_DIR after validation."""
    base_dir = get_base_dir()
    return os.path.normpath(os.path.join(base_dir, path))
