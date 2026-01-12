import logging
import os
import re
import uuid
from django.conf import settings
from hydra.tasks import cast_hydra_spell

logger = logging.getLogger(__name__)

def ai_read_file(file_path, root_path=None, max_chars=10000):
    """
    Reads a file from the disk safely within the specified root_path.
    """
    # 1. Determine Allowed Base
    # CRITICAL FIX: If logic provided a project root, USE IT.
    # Only fall back to BASE_DIR if absolutely necessary (internal debugging).
    if root_path:
        base_dir = os.path.normpath(str(root_path))
    else:
        # Fallback to settings.BASE_DIR (e.g. for reading self-diagnostics)
        # But really, this should almost always be the project root.
        base_dir = os.path.normpath(str(getattr(settings, 'BASE_DIR', 'c:/talos')))

    # 2. Resolve Full Path
    # Handle absolute paths (e.g. C:/Users/...) vs relative (Config/Default.ini)
    if os.path.isabs(file_path):
        full_path = os.path.normpath(file_path)
    else:
        full_path = os.path.normpath(os.path.join(base_dir, file_path))

    # 3. Security Check
    # Ensure the resolved path sits inside the authorized root
    # Use commonpath to ensure we are truly inside (handles case sensitivity on Windows better)
    try:
        common = os.path.commonpath([base_dir, full_path])
        if common.lower() != base_dir.lower():
            return f"Error: Access denied. Path '{full_path}' is outside the allowed root: '{base_dir}'"
    except ValueError:
        # commonpath raises ValueError if paths are on different drives
        return f"Error: Access denied. Path on different drive than root."

    if not os.path.exists(full_path):
        return f"Error: File '{file_path}' not found."

    if os.path.isdir(full_path):
        return f"Error: '{file_path}' is a directory."

    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(max_chars)
            if len(content) == max_chars:
                content += "\n... [TRUNCATED] ..."
            return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


def ai_search_file(file_path, pattern, root_path=None, context_lines=2):
    """
    Searches a file for a regex pattern safely within the root_path.
    """
    # 1. Security Setup (Same logic as read_file)
    if root_path:
        base_dir = os.path.normpath(str(root_path))
    else:
        base_dir = os.path.normpath(str(getattr(settings, 'BASE_DIR', 'c:/talos')))

    if os.path.isabs(file_path):
        full_path = os.path.normpath(file_path)
    else:
        full_path = os.path.normpath(os.path.join(base_dir, file_path))

    # 2. Security Check
    try:
        common = os.path.commonpath([base_dir, full_path])
        if common.lower() != base_dir.lower():
            return f"Error: Access denied. Path '{full_path}' is outside the allowed root: '{base_dir}'"
    except ValueError:
        return f"Error: Access denied. Path on different drive."

    if not os.path.exists(full_path):
        return f"Error: File not found at {full_path}"

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

                chunk = "".join([
                    f"{idx+1}: {l}"
                    for idx, l in enumerate(lines[start:end], start=start)
                ])
                results.append(f"--- Match {matches_found} (Line {i+1}) ---\n{chunk}")

                if len(results) >= 10:
                    results.append("... [Limit Reached. Refine search.]")
                    break

        if not results:
            return f"No matches found for pattern '{pattern}' in {file_path}."

        return "\n".join(results)
    except Exception as e:
        return f"Error searching file: {str(e)}"


def ai_execute_task(head_id):
    """
    Executes a specific Hydra Head (Spell).
    """
    try:
        val = uuid.UUID(str(head_id))
    except ValueError:
        return f"Error: Invalid Head ID '{head_id}'. Must be a UUID."

    try:
        cast_hydra_spell.delay(str(head_id))
        return f"Successfully queued spell for Head {head_id}. Monitor logs for progress."
    except Exception as e:
        return f"Error casting spell: {str(e)}"