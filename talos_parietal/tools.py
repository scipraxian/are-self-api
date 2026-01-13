import logging
import os
import re
import uuid
from django.conf import settings
from hydra.tasks import cast_hydra_spell

logger = logging.getLogger(__name__)


def _resolve_path(path, root_path):
    """
    Helper to resolve paths based on context.
    - If path is absolute: Use it directly (Power User override).
    - If path is relative: Join with root_path and ensure safety.
    """
    # 1. Determine Context Root
    if root_path:
        base_dir = os.path.normpath(str(root_path))
    else:
        # Default to Talos Root if no context provided
        base_dir = os.path.normpath(str(getattr(settings, 'BASE_DIR', 'c:/talos')))

    # 2. Handle Absolute Paths (The "Any file anywhere" rule)
    if os.path.isabs(path):
        full_path = os.path.normpath(path)
        if not os.path.exists(full_path):
            return None, f"Error: Absolute path '{path}' does not exist."
        return full_path, None

    # 3. Handle Relative Paths (The Sandbox)
    full_path = os.path.normpath(os.path.join(base_dir, path))

    # Security: Prevent '..' from escaping the root
    try:
        common = os.path.commonpath([base_dir, full_path])
        if common.lower() != base_dir.lower():
            return None, f"Error: Access denied. '{path}' traverses outside the context root."
    except ValueError:
        return None, f"Error: Access denied. Drive mismatch."

    if not os.path.exists(full_path):
        return None, f"Error: File '{path}' not found in context."

    return full_path, None


def ai_read_file(path, root_path=None, start_line=1, max_lines=50):
    """
    Reads a file slice.
    """
    full_path, error = _resolve_path(path, root_path)
    if error: return error

    if os.path.isdir(full_path):
        return f"Error: '{path}' is a directory. Use ai_list_files."

    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)
        start_idx = max(0, int(start_line) - 1)
        end_idx = start_idx + int(max_lines)
        chunk = lines[start_idx:end_idx]

        content = "".join([f"{i + 1}: {line}" for i, line in enumerate(chunk, start=start_idx)])

        footer = ""
        if end_idx < total_lines:
            footer = f"\n... [Displaying lines {start_idx+1}-{min(end_idx, total_lines)} of {total_lines}. Use start_line={end_idx+1} to read more.]"

        return content + footer

    except Exception as e:
        return f"Error reading file: {str(e)}"


def ai_search_file(path, pattern, root_path=None, context_lines=2):
    """
    Greps a file.
    """
    full_path, error = _resolve_path(path, root_path)
    if error: return error

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
                chunk = "".join([f"{idx + 1}: {l}" for idx, l in enumerate(lines[start:end], start=start)])
                results.append(f"--- Match {matches_found} (Line {i + 1}) ---\n{chunk}")

                if len(results) >= 10:
                    results.append("... [Limit Reached]")
                    break

        if not results:
            return f"No matches found for '{pattern}'."

        return "\n".join(results)
    except Exception as e:
        return f"Error searching file: {str(e)}"


def ai_list_files(path, root_path=None):
    """
    Lists directory contents.
    """
    full_path, error = _resolve_path(path, root_path)
    if error: return error

    if not os.path.isdir(full_path):
        return f"Error: '{path}' is not a directory."

    try:
        items = os.listdir(full_path)
        items.sort()

        result = [f"Listing for: {path}"]
        for item in items[:50]:
            item_path = os.path.join(full_path, item)
            kind = "[DIR] " if os.path.isdir(item_path) else "[FILE]"
            result.append(f"{kind} {item}")

        if len(items) > 50:
            result.append(f"... (and {len(items) - 50} more)")

        return "\n".join(result)
    except Exception as e:
        return f"Error listing directory: {str(e)}"


def ai_execute_task(head_id):
    try:
        val = uuid.UUID(str(head_id))
    except ValueError:
        return f"Error: Invalid Head ID '{head_id}'. Must be a UUID."

    try:
        cast_hydra_spell.delay(str(head_id))
        return f"Successfully queued spell for Head {head_id}."
    except Exception as e:
        return f"Error casting spell: {str(e)}"