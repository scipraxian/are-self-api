import os
import re

from asgiref.sync import sync_to_async
from django.conf import settings

# Configuration
MAX_FILES_SCANNED = 2000
MAX_OUTPUT_CHARS = 15000
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

import math


@sync_to_async
def _grep_sync(path: str,
               pattern: str,
               case_insensitive: bool = True,
               page: int = 1) -> str:
    """
    Implements a safe, recursive grep for the project.
    """
    if not os.path.exists(path):
        return f"Error: Path '{path}' does not exist."

    regex_flags = re.IGNORECASE if case_insensitive else 0

    matches = []
    errors = []
    files_scanned_count = 0
    hit_count_total = 0

    # 2. Generator for file discovery (Memory Efficient)
    def file_generator(root_path):
        if os.path.isfile(root_path):
            yield root_path
            return

        count = 0
        for root, dirs, files in os.walk(root_path):
            # In-place modify dirs to prune traversal
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

    # 3. Execution
    for filepath in file_generator(path):
        files_scanned_count += 1

        try:
            rel_path = os.path.relpath(filepath, path)

            # Read file with fallback encoding (skip binary-ish text)
            file_matches = []
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if re.search(pattern, line, regex_flags):
                            # Clean and truncate the line
                            content = line.strip()[:150]
                            file_matches.append(f'{i + 1}:{content}')
                            hit_count_total += 1
            except UnicodeDecodeError:
                continue

            if file_matches:
                # Add file header
                block_lines = [f'[{rel_path}]']
                # Add up to 10 matches per file
                block_lines.extend(file_matches[:10])
                if len(file_matches) > 10:
                    block_lines.append(
                        f'   ... ({len(file_matches) - 10} more matches in this file)'
                    )
                matches.append('\n'.join(block_lines))

        except Exception as e:
            # Capture errors instead of swallowing
            errors.append(f'Skipped {os.path.basename(filepath)}: {str(e)}')

    if not matches:
        status = f"grep: '{pattern}' not found in {files_scanned_count} files."
        if errors:
            status += f'\n(Note: Encountered {len(errors)} errors during scan, e.g., permissions).'
        return status

    matches_per_page = 20
    total_pages = math.ceil(len(matches) / matches_per_page) if matches else 1

    page = max(1, min(page, total_pages))
    start_index = (page - 1) * matches_per_page
    end_index = start_index + matches_per_page

    current_page_matches = matches[start_index:end_index]

    header = f"[GREP RESULTS: Page {page} of {total_pages} | Total Files Matched: {len(matches)} | Total Hits: {hit_count_total}]\n\n"

    output = header + '\n\n'.join(current_page_matches)

    # Clean truncation
    MAX_RETURN_CHARS = 20000
    if len(output) > MAX_RETURN_CHARS:
        output = output[:MAX_RETURN_CHARS].rsplit('\n', 1)[0]
        output += f'\n... [Truncated due to length]'

    return output


async def mcp_grep(path: str,
                   pattern: str,
                   case_insensitive: bool = True,
                   page: int = 1) -> str:
    """
    MCP Tool: grep -r.
    Recursively searches for a regex pattern starting at 'path'.
    """
    return await _grep_sync(path, pattern, case_insensitive, page)
