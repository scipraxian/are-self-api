"""Build distribution script for the UE project.

This script copies the staged build to multiple remote LAN targets, ensuring
that user saves are backed up and restored during the process.
"""

import logging
import os
import shutil
import subprocess
import sys

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
SOURCE_DIR = os.path.join(config.BUILD_ROOT, 'Windows')
TARGETS = config.REMOTE_TARGETS


def print_progress(current, total, prefix='Progress:', suffix='', length=40):
    """Prints a simple text progress bar to the console.

    Args:
        current (int): The current progress value.
        total (int): The total value for 100% progress.
        prefix (str): Prefix string for the progress bar.
        suffix (str): Suffix string for the progress bar.
        length (int): The character length of the progress bar.
    """
    percent = float(current) / float(total)
    arrow = '█' * int(round(percent * length))
    spaces = '-' * (length - len(arrow))
    sys.stdout.write(
        f'\r{prefix} |{arrow}{spaces}| {int(percent * 100)}% {suffix}'
    )
    sys.stdout.flush()


def get_tree_size(path):
    """Calculates the total size and file count of a directory tree.

    Args:
        path (str): The root directory to scan.

    Returns:
        tuple[int, int]: A tuple containing (total_size_bytes, total_file_count).
    """
    total = 0
    count = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
            count += 1
    return total, count


def copy_with_progress(src, dst):
    """Copies a directory tree while displaying a progress bar.

    Args:
        src (str): Source directory path.
        dst (str): Destination directory path.
    """
    if not os.path.exists(src):
        logger.error('[ERROR] Source not found: %s', src)
        return

    logger.info('   Calculating build size...')
    total_size, total_files = get_tree_size(src)
    logger.info(
        ' %d files (%s MB)', total_files, round(total_size / (1024 * 1024), 1)
    )

    if not os.path.exists(dst):
        os.makedirs(dst, exist_ok=True)

    copied_bytes = 0
    current_file_idx = 0

    for root, dirs, files in os.walk(src):
        rel_path = os.path.relpath(root, src)
        dest_dir = os.path.join(dst, rel_path)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        for f in files:
            src_file = os.path.join(root, f)
            dst_file = os.path.join(dest_dir, f)
            shutil.copy2(src_file, dst_file)

            file_size = os.path.getsize(src_file)
            copied_bytes += file_size
            current_file_idx += 1

            print_progress(
                copied_bytes,
                total_size,
                prefix='   Deploying:',
                suffix=f'({current_file_idx}/{total_files})',
                length=30
            )

    print()


def is_online(hostname):
    """Checks if a host is online using ICMP ping.

    Args:
        hostname (str): The hostname or IP to check.

    Returns:
        bool: True if the host is online, False otherwise.
    """
    try:
        subprocess.check_call(
            ['ping', '-n', '1', '-w', '200', hostname],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError:
        return False


def distribute_to_target(target):
    """Distributes the build to a single target machine.

    Args:
        target (dict): A dictionary containing target 'name' and UNC 'path'.
    """
    name = target['name']
    root_path = target['path']

    logger.info('\n--- Processing: %s (%s) ---', name, root_path)

    if not is_online(name):
        logger.warning('   [SKIP] Host \'%s\' is OFFLINE.', name)
        return

    remote_test = os.path.join(root_path, 'ReleaseTest')
    # Path assumes standard Unreal structure
    remote_game_saved = os.path.join(
        remote_test, config.PROJECT_NAME, 'Saved', 'SaveGames'
    )
    backup_dir = os.path.join(root_path, 'Temp_SaveBackup')

    # 1. BACKUP SAVES
    if os.path.exists(remote_game_saved):
        logger.info('   Backing up saves...')
        subprocess.run(
            ['robocopy', remote_game_saved, backup_dir, '/E', '/NJH', '/NJS',
             '/NFL', '/NDL'],
            shell=True,
            check=False
        )

    # 2. WIPE OLD BUILD
    if os.path.exists(remote_test):
        logger.info('   Wiping old build...')
        subprocess.run(f'rd /s /q "{remote_test}"', shell=True, check=False)

    # 3. COPY NEW BUILD
    if not os.path.exists(root_path):
        os.makedirs(root_path, exist_ok=True)

    copy_with_progress(SOURCE_DIR, remote_test)

    # 4. RESTORE SAVES
    if os.path.exists(backup_dir):
        logger.info('   Restoring saves...')
        subprocess.run(
            ['robocopy', backup_dir, remote_game_saved, '/E', '/NJH', '/NJS',
             '/NFL', '/NDL'],
            shell=True,
            check=False
        )
        subprocess.run(f'rd /s /q "{backup_dir}"', shell=True, check=False)

    logger.info('   [SUCCESS] Deployed to %s', name)


def main():
    """Main execution point for Step 6."""
    print('=' * 49)
    print('   6. DISTRIBUTE (Config Driven)')
    print('=' * 49)

    if not os.path.exists(SOURCE_DIR):
        logger.error('[ERROR] Source build not found at: %s', SOURCE_DIR)
        return

    for target in TARGETS:
        distribute_to_target(target)

    logger.info('\n[DONE] Distribution Complete.')


if __name__ == '__main__':
    main()