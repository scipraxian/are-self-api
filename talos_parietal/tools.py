import logging
import os
import re
import uuid
from django.conf import settings
from hydra.tasks import cast_hydra_spell

logger = logging.getLogger(__name__)


def ai_read_file(file_path, root_path=None, start_line=1, max_lines=50):
    """
    Reads a file from the disk safely within the specified root_path.
    Returns specific line ranges with line numbers.
    """
    # 1. Determine Allowed Base
    if root_path:
        base_dir = os.path.normpath(str(root_path))
    else:
        base_dir = os.path.normpath(str(getattr(settings, 'BASE_DIR', 'c:/talos')))

    # 2. Resolve Full Path
    if os.path.isabs(file_path):
        full_path = os.path.normpath(file_path)
    else:
        full_path = os.path.normpath(os.path.join(base_dir, file_path))

    # 3. Security Check
    try:
        common = os.path.commonpath([base_dir, full_path])
        if common.lower() != base_dir.lower():
            return f"Error: Access denied. Path '{full_path}' is outside the allowed root: '{base_dir}'"
    except ValueError:
        return f"Error: Access denied. Path on different drive."

    if not os.path.exists(full_path):
        return f"Error: File '{file_path}' not found."

    if os.path.isdir(full_path):
        return f"Error: '{file_path}' is a directory."

    # 4. Read Logic
    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)

        # Adjust 1-based user input to 0-based list index
        start_idx = max(0, int(start_line) - 1)
        end_idx = start_idx + int(max_lines)

        # Slice the file content
        chunk = lines[start_idx:end_idx]

        # FIX: enumerate start is the visual line number (start_idx + 1)
        # FIX: f-string uses {i}, not {i+1}, because i is already the correct line number
        content = "".join([f"{i}: {line}" for i, line in enumerate(chunk, start=start_idx + 1)])

        footer = ""
        if end_idx < total_lines:
            footer = f"\n... [Displaying lines {start_idx + 1}-{min(end_idx, total_lines)} of {total_lines}. Use start_line={end_idx + 1} to read more.]"

        return content + footer

    except Exception as e:
        return f"Error reading file: {str(e)}"


def ai_search_file(file_path, pattern, root_path=None, context_lines=2):
    """
    Searches a file for a regex pattern safely.
    """
    if root_path:
        base_dir = os.path.normpath(str(root_path))
    else:
        base_dir = os.path.normpath(str(getattr(settings, 'BASE_DIR', 'c:/talos')))

    if os.path.isabs(file_path):
        full_path = os.path.normpath(file_path)
    else:
        full_path = os.path.normpath(os.path.join(base_dir, file_path))

    try:
        common = os.path.commonpath([base_dir, full_path])
        if common.lower() != base_dir.lower():
            return f"Error: Access denied. Path '{full_path}' is outside the allowed root."
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
                # Context math
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)

                chunk = "".join([
                    f"{idx + 1}: {l}"
                    for idx, l in enumerate(lines[start:end], start=start + 1)  # +1 for 1-based lines
                ])
                results.append(f"--- Match {matches_found} (Line {i + 1}) ---\n{chunk}")

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