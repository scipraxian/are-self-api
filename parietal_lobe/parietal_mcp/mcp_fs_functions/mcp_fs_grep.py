import math
import os
import re

from asgiref.sync import sync_to_async

MAX_FILES_SCANNED = 2000
MAX_RETURN_CHARS = 20000
MATCHES_PER_PAGE = 20
MAX_MATCHES_PER_FILE = 10

SKIP_DIRS = {
    '.git',
    '.idea',
    '__pycache__',
    'venv',
    'node_modules',
    '.vscode',
    'site-packages',
    'migrations',
}

SKIP_EXTENSIONS = {
    '.pyc',
    '.exe',
    '.dll',
    '.so',
    '.db',
    '.sqlite3',
    '.png',
    '.jpg',
    '.ico',
    '.pdf',
}


def _file_generator(root_path):
    """Memory-efficient file discovery generator."""
    if os.path.isfile(root_path):
        yield root_path
        return

    count = 0
    for root, dirs, files in os.walk(root_path):
        dirs[:] = [
            d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')
        ]
        for file in files:
            if any(file.endswith(ext) for ext in SKIP_EXTENSIONS):
                continue
            yield os.path.join(root, file)
            count += 1
            if count >= MAX_FILES_SCANNED:
                return


def grep_sync(
    path: str,
    pattern: str,
    case_insensitive: bool = True,
    page: int = 1,
) -> str:
    """Implements a safe, recursive grep for the project."""
    if not os.path.exists(path):
        return f"Error: Path '{path}' does not exist."

    regex_flags = re.IGNORECASE if case_insensitive else 0

    matches = []
    errors = []
    files_scanned_count = 0
    hit_count_total = 0

    for filepath in _file_generator(path):
        files_scanned_count += 1

        try:
            rel_path = os.path.relpath(filepath, path)
            file_matches = []

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if re.search(pattern, line, regex_flags):
                            content = line.strip()[:150]
                            file_matches.append(f'{i + 1}:{content}')
                            hit_count_total += 1
            except UnicodeDecodeError:
                continue

            if file_matches:
                block_lines = [f'[{rel_path}]']
                block_lines.extend(file_matches[:MAX_MATCHES_PER_FILE])
                if len(file_matches) > MAX_MATCHES_PER_FILE:
                    remaining = len(file_matches) - MAX_MATCHES_PER_FILE
                    block_lines.append(
                        f'   ... ({remaining} more matches in this file)'
                    )
                matches.append('\n'.join(block_lines))

        except Exception as e:
            errors.append(
                f'Skipped {os.path.basename(filepath)}: {str(e)}'
            )

    if not matches:
        status = (
            f"grep: '{pattern}' not found in {files_scanned_count} files."
        )
        if errors:
            status += (
                f'\n(Note: Encountered {len(errors)} errors during scan, '
                f'e.g., permissions).'
            )
        return status

    total_pages = math.ceil(len(matches) / MATCHES_PER_PAGE) if matches else 1
    page = max(1, min(page, total_pages))
    start_index = (page - 1) * MATCHES_PER_PAGE
    end_index = start_index + MATCHES_PER_PAGE

    current_page_matches = matches[start_index:end_index]

    header = (
        f'[GREP RESULTS: Page {page} of {total_pages} | '
        f'Total Files Matched: {len(matches)} | '
        f'Total Hits: {hit_count_total}]\n\n'
    )

    output = header + '\n\n'.join(current_page_matches)

    if len(output) > MAX_RETURN_CHARS:
        output = output[:MAX_RETURN_CHARS].rsplit('\n', 1)[0]
        output += '\n... [Truncated due to length]'

    return output


_async_grep = sync_to_async(grep_sync)


async def execute(
    path: str,
    pattern: str,
    case_insensitive: bool = True,
    page: int = 1,
) -> str:
    """Recursively searches for a regex pattern starting at path."""
    return await _async_grep(path, pattern, case_insensitive, page)
