import asyncio
import os


def _patch_sync(
    path: str,
    content: str,
    start_line: int = 0,
    end_line: int = 0,
    create: bool = False,
) -> str:
    """
    Applies a surgical patch to a file.

    Modes:
    - Full write:  start_line=0 and end_line=0 → replaces entire file content.
    - Line replace: start_line and end_line specify the 1-indexed range to replace.
    - Create:       create=True → creates the file if it doesn't exist.
    """
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
    content: str,
    start_line: int = 0,
    end_line: int = 0,
    create: bool = False,
) -> str:
    """Writes or patches a file with surgical precision."""
    return await asyncio.to_thread(
        _patch_sync, path, content, start_line, end_line, create
    )
