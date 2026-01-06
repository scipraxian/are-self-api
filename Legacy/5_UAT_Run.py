"""UAT Runner script with user data preservation (Safe Harbor).

This script deploys the production build to a local test directory, injects
shader caches, and ensures user save games and configurations are preserved
across build deployments.
"""

import argparse
import logging
import os
import shutil
import subprocess
import time

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
DISTRO_SOURCE = os.path.join(config.BUILD_ROOT, 'Windows')
HARD_STORAGE = os.path.join(
    config.PSO_CACHE_DIR, f'{config.PROJECT_NAME}_PCD3D_SM6.spc'
)
TEST_DIR = config.RELEASE_TEST_DIR
GAME_EXE = os.path.join(TEST_DIR, f'{config.PROJECT_NAME}.exe')

# Internal Game Paths
GAME_SAVED_DIR = os.path.join(TEST_DIR, config.PROJECT_NAME, 'Saved')
SAVE_GAME_DIR = os.path.join(GAME_SAVED_DIR, 'SaveGames')
CONFIG_DIR = os.path.join(GAME_SAVED_DIR, 'Config')
CACHE_DEST = os.path.join(
    TEST_DIR, config.PROJECT_NAME, 'Content', 'PipelineCaches'
)

# EXTERNAL SAFE STORAGE (This folder is never deleted by the script)
SAFE_HARBOR_ROOT = os.path.join(config.BUILD_ROOT, 'User_Data_SafeHarbor')
SAFE_SAVES = os.path.join(SAFE_HARBOR_ROOT, 'SaveGames')
SAFE_CONFIG = os.path.join(SAFE_HARBOR_ROOT, 'Config')

LOG_ARCHIVE = os.path.join(config.LOG_DIR, 'UATApp.log')


def safe_copy_tree(src, dst):
    """Copies a directory tree, creating destination if needed.

    Iterates and copies to ensure we merge rather than replace.

    Args:
        src (str): Source directory path.
        dst (str): Destination directory path.
    """
    if not os.path.exists(src):
        return

    if not os.path.exists(dst):
        os.makedirs(dst)

    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            safe_copy_tree(s, d)
        else:
            try:
                shutil.copy2(s, d)
            except Exception as e:  # pylint: disable=broad-except
                logger.warning('[WARN] Failed to copy %s: %s', item, e)


def main():
    """Main deployment and launch logic."""
    parser = argparse.ArgumentParser()
    _, game_flags = parser.parse_known_args()

    print('=' * 49)
    print('   UAT RUNNER: SAFE HARBOR EDITION')
    print('=' * 49)

    # 2. BACKUP TO SAFE HARBOR
    if os.path.exists(SAVE_GAME_DIR) and os.listdir(SAVE_GAME_DIR):
        logger.info('[BACKUP] Syncing SaveGames to Safe Harbor...')
        safe_copy_tree(SAVE_GAME_DIR, SAFE_SAVES)
    else:
        logger.info(
            '[BACKUP] No active SaveGames found (or empty). '
            'Preserving Safe Harbor.'
        )

    if os.path.exists(CONFIG_DIR):
        logger.info('[BACKUP] Syncing Config to Safe Harbor...')
        safe_copy_tree(CONFIG_DIR, SAFE_CONFIG)

    # 3. DEPLOY BUILD (Wipe and Replace)
    logger.info('[DEPLOY] Wiping %s...', TEST_DIR)
    if os.path.exists(TEST_DIR):
        try:
            shutil.rmtree(TEST_DIR)
        except Exception:  # pylint: disable=broad-except
            time.sleep(1)
            try:
                shutil.rmtree(TEST_DIR, ignore_errors=True)
            except Exception as e:  # pylint: disable=broad-except
                logger.warning('[WARN] Wipe incomplete: %s', e)

    logger.info('[DEPLOY] Copying new build...')
    shutil.copytree(DISTRO_SOURCE, TEST_DIR)

    # 4. INJECT CACHE
    if os.path.exists(HARD_STORAGE):
        if not os.path.exists(CACHE_DEST):
            os.makedirs(CACHE_DEST)
        shutil.copy2(HARD_STORAGE, CACHE_DEST)

    # 5. RESTORE FROM SAFE HARBOR
    logger.info('[RESTORE] Restoring user data from Safe Harbor...')
    if os.path.exists(SAFE_SAVES):
        if not os.path.exists(SAVE_GAME_DIR):
            os.makedirs(SAVE_GAME_DIR)
        safe_copy_tree(SAFE_SAVES, SAVE_GAME_DIR)
        logger.info('   > Saves Restored.')

    if os.path.exists(SAFE_CONFIG):
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
        safe_copy_tree(SAFE_CONFIG, CONFIG_DIR)
        logger.info('   > Config Restored.')

    # 6. LAUNCH
    if os.path.exists(GAME_EXE):
        launch_cmd = [GAME_EXE, '-log', '-windowed', '-resX=1280', '-resY=720']

        if game_flags:
            logger.info('[LAUNCH] Adding flags: %s', game_flags)
            launch_cmd.extend(game_flags)

        logger.info('Launching: %s', launch_cmd)
        try:
            subprocess.run(launch_cmd, check=False)
        finally:
            # Rescue Log
            src = os.path.join(
                TEST_DIR, config.PROJECT_NAME, 'Saved', 'Logs',
                f'{config.PROJECT_NAME}.log'
            )
            if os.path.exists(src):
                try:
                    shutil.copy2(src, LOG_ARCHIVE)
                    logger.info('[LOG] Saved to %s', LOG_ARCHIVE)
                except Exception:  # pylint: disable=broad-except
                    pass


if __name__ == '__main__':
    main()