import asyncio
import os
from typing import Optional


def _resolve_path(path: str, root_path: str = None) -> tuple[
    Optional[str], Optional[str]]:
    from django.conf import settings
    base_dir = os.path.normpath(
        str(root_path or getattr(settings, 'BASE_DIR', 'c:/talos')))
    if os.path.isabs(path):
        full_path = os.path.normpath(path)
        return (full_path, None) if os.path.exists(full_path) else (None,
                                                                    f"Error: "
                                                                    f"'{path}' does not exist.")

    full_path = os.path.normpath(os.path.join(base_dir, path))
    try:
        if os.path.commonpath(
                [base_dir, full_path]).lower() != base_dir.lower():
            return None, f"Error: Access denied."
    except ValueError:
        return None, "Error: Drive mismatch."

    return (full_path, None) if os.path.exists(full_path) else (None,
                                                                f"Error: Path"
                                                                f" '{path}' "
                                                                f"not found.")


def _list_sync(full_path: str) -> str:
    if not os.path.isdir(full_path):
        return f"Error: '{full_path}' is not a directory."
    try:
        items = os.listdir(full_path)
        items.sort()
        result = [f"Listing for: {full_path}"]
        for item in items[:50]:
            item_path = os.path.join(full_path, item)
            kind = "[DIR] " if os.path.isdir(item_path) else "[FILE]"
            result.append(f"{kind} {item}")
        if len(items) > 50:
            result.append(f"... (and {len(items) - 50} more)")
        return "\n".join(result)
    except Exception as e:
        return f"Error listing directory: {str(e)}"


async def mcp_list_files(path: str, root_path: str = None) -> str:
    """MCP Tool: Lists directory contents."""
    full_path, error = _resolve_path(path, root_path)
    if error: return error
    return await asyncio.to_thread(_list_sync, full_path)
