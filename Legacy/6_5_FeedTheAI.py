"""Context packer script to generate input for AI analysis.

This script traverses project directories, reads source, config, and pipeline
files, and aggregates them into a single context log file with truncation for
large files.
"""

import datetime
import logging
import os

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration ---
OUTPUT_FILENAME_ROOT = 'HSH_Full_Context'

EXTENSIONS_TO_PROCESS = {
    '.cpp', '.h', '.cs', '.py', '.bat', '.json', '.ini', '.uproject', '.log'
}
DIRECTORIES_TO_IGNORE = {
    '.git', '.vs', 'Intermediate', 'Binaries', 'Saved', 'DerivedDataCache',
    'Build', 'Content', '__pycache__', 'External'
}
HEAD_LINE_COUNT = 1000
TAIL_LINE_COUNT = 1000


def get_output_file_path() -> str:
    """Generates a timestamped output file path for the context dump.

    Returns:
        str: The absolute path to the output log file.
    """
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{OUTPUT_FILENAME_ROOT}_{timestamp}.log'
    return os.path.join(config.LOG_DIR, filename)


def is_target_file(filename: str) -> bool:
    """Checks if a file extension is in the target list for processing.

    Args:
        filename (str): The filename to check.

    Returns:
        bool: True if the file should be processed, False otherwise.
    """
    return any(filename.lower().endswith(ext) for ext in EXTENSIONS_TO_PROCESS)


def is_context_log_file(filename: str) -> bool:
    """Checks if a file is an existing context dump file.

    Args:
        filename (str): The filename to check.

    Returns:
        bool: True if the file is a context dump, False otherwise.
    """
    return filename.startswith(OUTPUT_FILENAME_ROOT)


def read_file_with_truncation(
    file_path: str, head_count: int, tail_count: int
) -> str:
    """Reads a file and truncates the middle portion if it exceeds limits.

    Args:
        file_path (str): Path to the file to read.
        head_count (int): Number of lines to keep from the start.
        tail_count (int): Number of lines to keep from the end.

    Returns:
        str: The (potentially truncated) content of the file.
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        if len(lines) <= (head_count + tail_count):
            return "".join(lines)

        truncated = lines[:head_count]
        truncated.append(
            f'\n... [TRUNCATED: {len(lines) - (head_count + tail_count)} '
            'lines removed] ...\n\n'
        )
        truncated.extend(lines[-tail_count:])
        return "".join(truncated)

    except Exception as e:  # pylint: disable=broad-except
        return f'[ERROR reading {file_path}: {e}]'


def process_directory_tree(root_dir: str, label: str, output_handle):
    """Walks a directory tree and writes target file contents to the output.

    Args:
        root_dir (str): The directory to walk.
        label (str): A label for the section in the output file.
        output_handle (file): The open file handle to write to.
    """
    logger.info('Scanning %s: %s...', label, root_dir)
    output_handle.write(f'\n\n=== SECTION: {label} ===\n')

    for current_root, dirs, files in os.walk(root_dir):
        # Filter directories in-place for os.walk
        dirs[:] = sorted([d for d in dirs if d not in DIRECTORIES_TO_IGNORE])

        for filename in sorted(files):
            if is_context_log_file(filename):
                continue
            if not is_target_file(filename):
                continue

            full_path = os.path.join(current_root, filename)
            relative_path = os.path.relpath(full_path, root_dir)

            if filename.endswith('.log') and 'Logs' in current_root:
                logger.info('   [LOG DETECTED] Packing: %s', filename)

            content = read_file_with_truncation(
                full_path, HEAD_LINE_COUNT, TAIL_LINE_COUNT
            )
            output_handle.write(f'\n\n--- FILE: {label}/{relative_path} ---\n')
            output_handle.write(content)


def main():
    """Main execution point for Step 6.5."""
    print('=' * 49)
    print(' STEP 6.5: FEED THE AI (Context Packer)')
    print('=' * 49)

    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        output_path = get_output_file_path()

        with open(output_path, 'w', encoding='utf-8') as outfile:
            outfile.write('PROJECT CONTEXT DUMP\n')
            outfile.write(f'Generated for: {config.PROJECT_NAME}\n')
            outfile.write(f'Timestamp: {datetime.datetime.now()}\n')

            # 1. Source
            source_dir = os.path.join(config.PROJECT_ROOT, 'Source')
            if os.path.exists(source_dir):
                process_directory_tree(source_dir, 'SOURCE', outfile)
            # 2. Config
            config_dir = os.path.join(config.PROJECT_ROOT, 'Config')
            if os.path.exists(config_dir):
                process_directory_tree(config_dir, 'CONFIG', outfile)
            # 3. Pipeline
            process_directory_tree(config.BUILDER_DIR, 'PIPELINE', outfile)

        logger.info('[DONE] Context packed into: %s', output_path)

    except Exception as e:  # pylint: disable=broad-except
        logger.error('[FATAL ERROR] %s', e)


if __name__ == '__main__':
    main()