import logging
import os
import re  # <--- RESTORED
import uuid  # <--- RESTORED

from django.conf import settings

from central_nervous_system.models import Spike
from central_nervous_system.tasks import fire_spike

logger = logging.getLogger(__name__)


def _resolve_path(path, root_path):
    """
    Helper to resolve paths based on context.
    - If path is absolute: Use it directly (Power User override / Bypass Sandbox).
    - If path is relative: Join with root_path and ENFORCE sandbox.
    """
    # 1. Determine Context Root
    if root_path:
        base_dir = os.path.normpath(str(root_path))
    else:
        base_dir = os.path.normpath(str(settings.BASE_DIR))

    # 2. Handle Absolute Paths (BYPASS SANDBOX)
    if os.path.isabs(path):
        full_path = os.path.normpath(path)
        if not os.path.exists(full_path):
            return None, f"Error: Absolute path '{path}' does not exist."
        return full_path, None

    # 3. Handle Relative Paths (ENFORCE SANDBOX)
    full_path = os.path.normpath(os.path.join(base_dir, path))

    # Security Check
    try:
        common = os.path.commonpath([base_dir, full_path])
        if common.lower() != base_dir.lower():
            return (
                None,
                f"Error: Access denied. '{path}' is outside the context root.",
            )
    except ValueError:
        return None, f'Error: Access denied. Partition/Drive mismatch.'

    if not os.path.exists(full_path):
        return None, f"Error: Path '{path}' not found."

    return full_path, None


def ai_read_file(path, root_path=None, start_line=1, max_lines=50):
    full_path, error = _resolve_path(path, root_path)
    if error:
        return error

    if os.path.isdir(full_path):
        return f"Error: '{path}' is a directory. Use ai_list_files."

    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)
        start_idx = max(0, int(start_line) - 1)
        end_idx = start_idx + int(max_lines)
        chunk = lines[start_idx:end_idx]

        content = ''.join(
            [
                f'{i + 1}: {line}'
                for i, line in enumerate(chunk, start=start_idx)
            ]
        )

        footer = ''
        if end_idx < total_lines:
            footer = f'\n... [Displaying lines {start_idx + 1}-{min(end_idx, total_lines)} of {total_lines}. Use start_line={end_idx + 1} to read more.]'

        return content + footer

    except Exception as e:
        return f'Error reading file: {str(e)}'


def ai_search_file(path, pattern, root_path=None, context_lines=2):
    full_path, error = _resolve_path(path, root_path)
    if error:
        return error

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
                chunk = ''.join(
                    [
                        f'{idx + 1}: {l}'
                        for idx, l in enumerate(lines[start:end], start=start)
                    ]
                )
                results.append(
                    f'--- Match {matches_found} (Line {i + 1}) ---\n{chunk}'
                )

                if len(results) >= 10:
                    results.append('... [Limit Reached]')
                    break

        if not results:
            return f"No matches found for '{pattern}'."

        return '\n'.join(results)
    except Exception as e:
        return f'Error searching file: {str(e)}'


def ai_list_files(path, root_path=None):
    full_path, error = _resolve_path(path, root_path)
    if error:
        return error

    if not os.path.isdir(full_path):
        return f"Error: '{path}' is not a directory."

    try:
        items = os.listdir(full_path)
        items.sort()

        result = [f'Listing for: {full_path}']
        for item in items[:50]:
            item_path = os.path.join(full_path, item)
            kind = '[DIR] ' if os.path.isdir(item_path) else '[FILE]'
            result.append(f'{kind} {item}')

        if len(items) > 50:
            result.append(f'... (and {len(items) - 50} more)')

        return '\n'.join(result)
    except Exception as e:
        return f'Error listing directory: {str(e)}'


def ai_execute_task(spike_id):
    try:
        val = uuid.UUID(str(spike_id))
    except ValueError:
        return f"Error: Invalid Spike ID '{spike_id}'. Must be a UUID."
    try:
        fire_spike.delay(str(spike_id))
        return f'Successfully queued effector for Spike {spike_id}.'
    except Exception as e:
        return f'Error casting effector: {str(e)}'


def ai_update_blackboard(spike_id: str, key: str, value: str) -> str:
    """
    Updates a value in the Spike blackboard, altering the state
    for downstream graph routing.
    """

    try:
        val_uuid = uuid.UUID(str(spike_id))
    except ValueError:
        return f"Error: Invalid Spike ID '{spike_id}'. Must be a UUID."

    try:
        spike = Spike.objects.get(id=val_uuid)

        # Guard against uninitialized JSON fields
        if not isinstance(spike.blackboard, dict):
            spike.blackboard = {}

        spike.blackboard[key] = value
        spike.save(update_fields=['blackboard'])

        logger.info(
            f'[Parietal] Blackboard mutated for Spike {spike_id}: {key}={value}'
        )
        return f"Success: Blackboard updated. {key} is now '{value}'."

    except Spike.DoesNotExist:
        return f'Error: Spike {spike_id} not found.'
    except Exception as e:
        logger.error(f'[Parietal] Blackboard update failed: {e}')
        return f'Error updating blackboard: {str(e)}'
