"""Staging run script to record PSO data and compile shaders.

This script launches the staged game with specific flags to ensure PSO data
is recorded and shaders are compiled, then archives the resulting logs.
"""

import logging
import os
import shutil
import subprocess
import sys

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

# --- DERIVED CONFIGURATION ---
# Assumes standard Unreal staging structure: Windows/ProjectName.exe
GAME_EXE = os.path.join(
    config.STAGING_DIR, 'Windows', f'{config.PROJECT_NAME}.exe'
)
SOURCE_LOG = os.path.join(
    config.STAGING_DIR, 'Windows', config.PROJECT_NAME, 'Saved', 'Logs',
    f'{config.PROJECT_NAME}.log'
)
DEST_LOG = os.path.join(config.LOG_DIR, 'StagingApp.log')


def main():
    """Launches the staged game and archives the log."""
    print('=' * 49)
    print(' STEP 2: STAGING RUN (Auto-Compile & Record)')
    print('=' * 49)

    if not os.path.exists(GAME_EXE):
        logger.error('[ERROR] Executable not found at: %s', GAME_EXE)
        sys.exit(1)

    cmd = [
        GAME_EXE,
        '-log',
        '-logPSO',
        '-clearPSODriverCache',
        '-CompileShaders',
        '-windowed',
        '-resX=1280',
        '-resY=720'
    ]

    logger.info('Launching Game...')
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        logger.info('[Info] Game process finished.')

    logger.info('[Log] Copying log to %s...', DEST_LOG)
    if os.path.exists(SOURCE_LOG):
        shutil.copy2(SOURCE_LOG, DEST_LOG)
    else:
        logger.warning('[WARNING] Log file missing at %s', SOURCE_LOG)


if __name__ == '__main__':
    main()