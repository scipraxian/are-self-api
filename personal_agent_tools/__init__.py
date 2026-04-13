"""
Synchronous helpers for child Python processes (mcp_code_exec).

These wrap Are-Self MCP filesystem primitives; they are not copied from Hermes.
"""
import subprocess
from typing import Any, Dict, Optional

__all__ = [
    'read_file',
    'write_file',
    'search_files',
    'terminal',
    'patch',
]


def read_file(path: str, page: int = 1) -> str:
    """Read a paginated text slice from a file (same behavior as mcp_fs read)."""
    from parietal_lobe.parietal_mcp.mcp_fs_functions.mcp_fs_read import _read_sync

    return _read_sync(path, int(page))


def write_file(path: str, content: str) -> Dict[str, Any]:
    """Write under BASE_DIR (relative path). Returns structured result."""
    from parietal_lobe.parietal_mcp.mcp_fs_write import _write_sync

    return _write_sync(path, content)


def search_files(
    path: str,
    pattern: str,
    case_insensitive: bool = True,
    page: int = 1,
) -> str:
    """Recursive regex search (same behavior as mcp_fs grep)."""
    from parietal_lobe.parietal_mcp.mcp_fs_functions.mcp_fs_grep import grep_sync

    return grep_sync(path, pattern, case_insensitive, page)


def terminal(
    command: str,
    timeout: int = 180,
    workdir: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a shell command synchronously."""
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=workdir,
    )
    return {
        'stdout': completed.stdout,
        'stderr': completed.stderr,
        'exit_code': completed.returncode,
    }


def patch(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> Dict[str, Any]:
    """Fuzzy string patch (same engine as mcp_fs patch with old_string)."""
    from parietal_lobe.parietal_mcp.mcp_fs_functions.mcp_fs_patch import (
        apply_string_patch_sync,
    )

    return apply_string_patch_sync(path, old_string, new_string, replace_all)
