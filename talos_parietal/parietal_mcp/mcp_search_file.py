import asyncio
import os
import re
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


def _search_sync(full_path: str, pattern: str, context_lines: int = 2) -> str:
    if os.path.isdir(full_path): return f"Error: '{full_path}' is a directory."
    results = []
    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        matches_found = 0
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE):
                matches_found += 1
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                chunk = "".join([f"{idx + 1}: {l}" for idx, l in
                                 enumerate(lines[start:end], start=start)])
                results.append(
                    f"--- Match {matches_found} (Line {i + 1}) ---\n{chunk}")
                if len(results) >= 10:
                    results.append("... [Limit Reached]")
                    break
        return "\n".join(
            results) if results else f"No matches found for '{pattern}'."
    except Exception as e:
        return f"Error searching file: {str(e)}"


async def mcp_search_file(path: str, pattern: str,
                          root_path: str = None) -> str:
    """MCP Tool: Searches a file for a regex pattern."""
    full_path, error = _resolve_path(path, root_path)
    if error: return error
    return await asyncio.to_thread(_search_sync, full_path, pattern)
