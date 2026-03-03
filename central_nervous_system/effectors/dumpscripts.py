#!/usr/bin/env python3
"""Talos Spell: Script Dumper.

Concatenates source files from a target directory and streams them to stdout.
Used by the Peripheral Nervous System to provide context for AI reasoning sessions.
"""

import logging
import os
import sys
from typing import Set

EXTENSIONS_TO_PROCESS: Set[str] = {
    '.cpp',
    '.h',
    '.cs',
    '.py',
    '.bat',
    '.json',
    '.ini',
    '.uproject',
    '.log',
    '.css',
    '.html',
    '.js',
    '.md',
}

DIRECTORIES_TO_IGNORE: Set[str] = {
    '.git',
    '.vs',
    'Intermediate',
    'Binaries',
    'Saved',
    'DerivedDataCache',
    'Build',
    'Content',
    '__pycache__',
    'External',
    'venv',
    '.junie',
    '.agent',
}

# Logger setup as per standards
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stderr,  # Stream logs to stderr so stdout remains clean for data
)
logger = logging.getLogger('dumpscripts')


def _is_target_file(filename: str) -> bool:
    """Checks if a file extension is in the supported list."""
    return any(filename.lower().endswith(ext) for ext in EXTENSIONS_TO_PROCESS)


def _process_file(full_path: str, relative_path: str) -> None:
    """Reads a file and writes its content to stdout with header."""
    try:
        # Standard header format for Talos concatenation [cite: 26319]
        sys.stdout.write('\n' + '=' * 80 + '\n')
        sys.stdout.write(f'FILE: {relative_path}\n')
        sys.stdout.write('=' * 80 + '\n\n')

        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            # sys.stdout.write is used for direct streaming to the effector stream
            sys.stdout.write(f.read())
            sys.stdout.write('\n')
            sys.stdout.flush()

    except Exception as e:
        logger.error(f'Error reading {full_path}: {e}')


def dump_directory_tree(root_dir: str) -> None:
    """Walks the directory tree and dumps relevant source files.

    Args:
        root_dir: The starting directory for concatenation.
    """
    if not os.path.isdir(root_dir):
        logger.error(f'Target directory does not exist: {root_dir}')
        sys.exit(1)

    # Section header for the effector stream
    sys.stdout.write(f'TALOS CONCATENATED SOURCE DUMP\n')
    sys.stdout.write(f'START_PATH: {os.path.abspath(root_dir)}\n')

    for current_root, dirs, files in os.walk(root_dir):
        # Filter directories in-place to respect standard ignore lists [cite: 26320]
        dirs[:] = [d for d in dirs if d not in DIRECTORIES_TO_IGNORE]

        for filename in sorted(files):
            if not _is_target_file(filename):
                continue

            full_path = os.path.join(current_root, filename)
            relative_path = os.path.relpath(full_path, root_dir)

            _process_file(full_path, relative_path)


def main() -> None:
    """Main entry point for the dumpscripts effector."""
    # Ensure stdout and stderr handle UTF-8 even on Windows terminals
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    if len(sys.argv) < 2:
        logger.error('Usage: python dumpscripts.py <root_directory>')
        sys.exit(1)

    target_dir = sys.argv[1]
    dump_directory_tree(target_dir)
    sys.exit(0)


if __name__ == '__main__':
    main()
