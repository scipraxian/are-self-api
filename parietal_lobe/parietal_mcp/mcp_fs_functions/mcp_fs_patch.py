"""
Surgical file patch: full write, line range, or fuzzy old_string replacement.
"""
import ast
import asyncio
import json
import os
from typing import Any, Dict

from parietal_lobe.parietal_mcp.fs_path_policy import (
    resolve_write_path,
    validate_write_path_under_base,
)
from parietal_lobe.parietal_mcp.mcp_fs_functions.fuzzy_match import (
    apply_replacement,
)


def apply_string_patch_sync(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> Dict[str, Any]:
    """
    Hermes_tools entry: fuzzy replace in file at path (relative to BASE_DIR).

    Returns:
        Result dict with ok, path, strategy_used, new_content (optional), error.
    """
    err = validate_write_path_under_base(path)
    if err:
        return {'ok': False, 'error': err}

    full_path = resolve_write_path(path)
    if not os.path.exists(full_path):
        return {'ok': False, 'error': f"Error: '{path}' does not exist."}
    if os.path.isdir(full_path):
        return {'ok': False, 'error': f"Error: '{path}' is a directory."}

    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as handle:
            original = handle.read()
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}

    try:
        new_content, strategy_used = apply_replacement(
            original,
            old_string,
            new_string,
            replace_all,
        )
    except ValueError as exc:
        return {'ok': False, 'error': str(exc)}

    try:
        with open(full_path, 'w', encoding='utf-8') as handle:
            handle.write(new_content)
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}

    return {
        'ok': True,
        'path': path,
        'strategy_used': strategy_used,
    }


def _run_syntax_hook(hook_name: str, text: str) -> str | None:
    """Returns error message if validation fails, else None."""
    if not hook_name or hook_name.lower() in ('', 'none', 'noop'):
        return None
    if hook_name.lower() == 'python':
        try:
            ast.parse(text)
        except SyntaxError as exc:
            return f'Python syntax validation failed: {exc}'
        return None
    return f'Unknown syntax_validation_hook: {hook_name}'


def _patch_sync(
    path: str,
    content: str,
    start_line: int = 0,
    end_line: int = 0,
    create: bool = False,
    old_string: str = '',
    new_string: str = '',
    replace_all: bool = False,
    syntax_validation_hook: str = '',
) -> str:
    """
    Applies a surgical patch to a file.

    Modes:
    - Fuzzy: old_string non-empty → fuzzy replace with new_string.
    - Full write:  start_line=0 and end_line=0 → replaces entire file content.
    - Line replace: start_line and end_line specify the 1-indexed range.
    - Create:       create=True → creates the file if it doesn't exist.
    """
    if old_string:
        result = apply_string_patch_sync(
            path,
            old_string,
            new_string,
            replace_all,
        )
        if not result.get('ok'):
            return json.dumps(result)

        if syntax_validation_hook:
            full_path = resolve_write_path(path)
            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as handle:
                    written = handle.read()
            except OSError as exc:
                return json.dumps({'ok': False, 'error': str(exc)})
            hook_err = _run_syntax_hook(syntax_validation_hook, written)
            if hook_err:
                return json.dumps({'ok': False, 'error': hook_err})

        out = {
            'ok': True,
            'path': result['path'],
            'strategy_used': result['strategy_used'],
        }
        return json.dumps(out)

    parent_dir = os.path.dirname(path)

    if not os.path.exists(path):
        if not create:
            return (
                f"Error: '{path}' does not exist. "
                f"Set create=True to create it."
            )
        if parent_dir and not os.path.isdir(parent_dir):
            return f"Error: Parent directory '{parent_dir}' does not exist."

    if os.path.isdir(path):
        return f"Error: '{path}' is a directory."

    try:
        if start_line > 0 and end_line > 0:
            return _apply_line_patch(path, content, start_line, end_line)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

        verb = 'Created' if create and not os.path.exists(path) else 'Written'
        return f'Success: {verb} {len(content)} chars to {path}.'

    except Exception as e:
        return f'Error patching file: {str(e)}'


def _apply_line_patch(
    path: str,
    content: str,
    start_line: int,
    end_line: int,
) -> str:
    """Replaces a specific line range in an existing file."""
    if not os.path.exists(path):
        return f"Error: '{path}' does not exist for line patching."

    if start_line < 1:
        return 'Error: start_line must be >= 1.'
    if end_line < start_line:
        return 'Error: end_line must be >= start_line.'

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)
        if start_line > total_lines:
            return (
                f'Error: start_line {start_line} exceeds '
                f'file length ({total_lines} lines).'
            )

        safe_end = min(end_line, total_lines)
        start_idx = start_line - 1

        replacement_lines = content.splitlines(keepends=True)
        if replacement_lines and not replacement_lines[-1].endswith('\n'):
            replacement_lines[-1] += '\n'

        lines[start_idx:safe_end] = replacement_lines

        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return (
            f'Success: Replaced lines {start_line}-{safe_end} '
            f'with {len(replacement_lines)} new lines.'
        )

    except Exception as e:
        return f'Error applying line patch: {str(e)}'


async def execute(
    path: str,
    content: str = '',
    start_line: int = 0,
    end_line: int = 0,
    create: bool = False,
    old_string: str = '',
    new_string: str = '',
    replace_all: bool = False,
    syntax_validation_hook: str = '',
) -> str:
    """Writes or patches a file with surgical precision."""
    return await asyncio.to_thread(
        _patch_sync,
        path,
        content,
        start_line,
        end_line,
        create,
        old_string,
        new_string,
        replace_all,
        syntax_validation_hook,
    )
