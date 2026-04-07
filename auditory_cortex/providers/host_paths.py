"""Host path bridging for local speech binaries (WSL / Windows interop)."""

import os
import shutil
import subprocess
import tempfile
from typing import Optional


def is_windows_interop_runtime() -> bool:
    """Return True if wslpath is available (WSL) or on native Windows."""
    if os.name == 'nt':
        return True
    return shutil.which('wslpath') is not None


def wsl_to_win(path: str) -> str:
    """Convert a WSL Linux path to a native Windows path when possible."""
    path = os.path.abspath(os.path.expanduser(path))
    try:
        result = subprocess.run(
            ['wslpath', '-w', path],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    if path.startswith('/mnt/c/'):
        return 'C:/' + path[len('/mnt/c/') :]
    return path


def to_provider_path(path: str, runtime: str) -> str:
    """Normalize path for a provider runtime ('wsl', 'win', 'posix')."""
    cleaned = os.path.abspath(os.path.expanduser(path))
    if runtime == 'win' and os.name != 'nt':
        return wsl_to_win(cleaned)
    return cleaned


def provider_writable_temp(runtime: str, ext: str) -> str:
    """Return a writable temp path for synthesized audio (best-effort)."""
    suffix = ext if ext.startswith('.') else '.%s' % (ext,)
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    if runtime == 'win':
        return wsl_to_win(name)
    return name
