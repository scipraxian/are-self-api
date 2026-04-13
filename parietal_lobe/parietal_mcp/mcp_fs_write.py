"""
MCP tool: write file content under the project root (relative paths only).
"""
import asyncio
import os
from typing import Any, Dict

from parietal_lobe.parietal_mcp.fs_path_policy import (
    resolve_write_path,
    validate_write_path_under_base,
)


def _write_sync(path: str, content: str) -> Dict[str, Any]:
    """Creates parent dirs, overwrites file, returns bytes written."""
    err = validate_write_path_under_base(path)
    if err:
        return {'ok': False, 'error': err}

    full_path = resolve_write_path(path)
    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    data = content.encode('utf-8')
    with open(full_path, 'wb') as handle:
        handle.write(data)

    return {
        'ok': True,
        'path': path,
        'bytes_written': len(data),
    }


async def mcp_fs_write(
    path: str,
    content: str,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Write content to a file under BASE_DIR; parents are created as needed."""
    return await asyncio.to_thread(_write_sync, path, content)
