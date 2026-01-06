"""Maintenance script to clean build artifacts and regenerate project files.

This script deletes common Unreal Engine artifact directories (Binaries,
Intermediate, Cooked, PipelineCaches) and runs the Unreal Build Tool (UBT)
to regenerate Visual Studio project files.
"""

import logging
import os
import shutil
import subprocess
import sys

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

# --- DERIVED TARGETS ---
LOG_FILE = os.path.join(config.LOG_DIR, 'Maintenance_Clean.log')

TARGETS = [
    os.path.join(config.PROJECT_ROOT, 'Binaries'),
    os.path.join(config.PROJECT_ROOT, 'Intermediate'),
    os.path.join(config.PROJECT_ROOT, 'Saved', 'Cooked'),
    os.path.join(config.PROJECT_ROOT, 'Build', 'Windows', 'PipelineCaches')
]


def clean_artifacts():
    """Main function to perform the deep clean and regeneration."""
    # Setup file logging manually to capture all output if needed,
    # or just use standard logging.
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    print('=' * 49)
    print(' MAINTENANCE: DEEP CLEAN & REGENERATE')
    print('=' * 49)

    # 1. The Purge
    logger.info('\n[1/2] Wiping Artifacts...')
    for path in TARGETS:
        if os.path.exists(path):
            logger.info('   [Deleting] %s', path)
            try:
                if os.path.isfile(path):
                    os.remove(path)
                else:
                    shutil.rmtree(path)
            except OSError as e:
                logger.error('      [ERROR] Access Denied: %s', e)
                return
        else:
            logger.info('   [Skipping] %s (Already Clean)', path)

    # 2. The Regeneration
    logger.info('\n[2/2] Regenerating Project Files...')
    cmd = [
        config.UBT_EXE,
        '-projectfiles',
        f'-project={config.UPROJECT_PATH}',
        '-game',
        '-rocket',
        '-progress'
    ]

    try:
        logger.info('   Running UBT: %s', config.UBT_EXE)
        # Using shell=False is preferred unless needed
        subprocess.run(cmd, check=True)
        logger.info('\n[SUCCESS] Project files regenerated.')
    except subprocess.CalledProcessError:
        logger.error('\n[ERROR] Failed to generate project files.')


if __name__ == '__main__':
    clean_artifacts()