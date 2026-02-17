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
                                                                    f"Absolute path '{path}' does not exist.")

    full_path = os.path.normpath(os.path.join(base_dir, path))
    try:
        if os.path.commonpath(
                [base_dir, full_path]).lower() != base_dir.lower():
            return None, (f"Error: Access denied. '{path}' is outside the "
                          f"context root.")
    except ValueError:
        return None, "Error: Access denied. Partition/Drive mismatch."

    return (full_path, None) if os.path.exists(full_path) else (None,
                                                                f"Error: Path "
                                                                f"'{path}' "
                                                                f"not found.")


def _read_sync(full_path: str, start_line: int, max_lines: int) -> str:
    if os.path.isdir(full_path):
        return f"Error: '{full_path}' is a directory. Use mcp_list_files."
    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        total_lines = len(lines)
        start_idx = max(0, start_line - 1)
        end_idx = start_idx + max_lines
        chunk = lines[start_idx:end_idx]

        content = "".join([f"{i + 1}: {line}" for i, line in
                           enumerate(chunk, start=start_idx)])
        if end_idx < total_lines:
            content += (f"\n... [Displaying lines {start_idx + 1}-"
                        f"{min(end_idx, total_lines)} of {total_lines}. Use"
                        f" start_line={end_idx + 1} to read more.]")
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


async def mcp_read_file(path: str, start_line: int = 1, max_lines: int = 50,
                        root_path: str = None) -> str:
    """MCP Tool: Reads a specific line range from a file."""
    full_path, error = _resolve_path(path, root_path)
    if error: return error
    return await asyncio.to_thread(_read_sync, full_path, start_line, max_lines)
