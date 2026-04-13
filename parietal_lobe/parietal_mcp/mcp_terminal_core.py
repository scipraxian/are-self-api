"""
Shared helpers for mcp_terminal / poll / kill.
"""
import logging
import os
import re
import subprocess
import sys
import tempfile
import uuid
from typing import Any, Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 50 * 1024

DANGEROUS_PATTERNS = (
    (re.compile(r'(^|[;&|])\s*sudo\b'), 'sudo'),
    (re.compile(r'rm\s+-rf\s+/'), 'rm -rf /'),
    (re.compile(r'\bmkfs\b'), 'mkfs'),
    (re.compile(r'\bdd\s+.*\bif='), 'dd if='),
    (re.compile(r':\(\)\s*\{\s*:\|:&\s*\}\s*;:\s*'), 'fork bomb'),
    (re.compile(r'>\s*/etc/passwd'), '> /etc/passwd'),
)


def detect_dangerous(command: str) -> Optional[str]:
    """Return a human-readable reason if the command looks dangerous."""
    stripped = command.strip()
    for pattern, label in DANGEROUS_PATTERNS:
        if pattern.search(stripped):
            return label
    return None


def truncate_output(text: str) -> Tuple[str, bool]:
    """Truncate to MAX_OUTPUT_CHARS; returns (text, truncated_flag)."""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    return (
        text[:MAX_OUTPUT_CHARS]
        + '\n... [Output truncated at %s chars]' % MAX_OUTPUT_CHARS,
        True,
    )


def popen_kwargs(workdir: Optional[str]) -> Dict[str, Any]:
    """Platform-specific kwargs for background subprocess."""
    kwargs: Dict[str, Any] = {
        'shell': True,
        'cwd': workdir or None,
    }
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    return kwargs


def log_path_for_session(session_id: Union[uuid.UUID, str]) -> str:
    """Temp log path for a background shell session."""
    return os.path.join(
        tempfile.gettempdir(),
        'parietal_terminal_%s.log' % session_id,
    )


def process_is_running(pid: int) -> bool:
    """Return True if pid appears to be running."""
    if sys.platform == 'win32':
        try:
            out = subprocess.run(
                ['tasklist', '/FI', 'PID eq %s' % pid],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return str(pid) in out.stdout
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_log_tail(path: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Read tail of log file."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            data = handle.read()
        if len(data) > max_chars:
            return data[-max_chars:]
        return data
    except OSError as exc:
        logger.warning('[mcp_terminal] Log read failed: %s', exc)
        return ''
