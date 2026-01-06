"""Shader cache processing script for the UE project.

This script identifies recorded PSO data (.rec files) and uses the Unreal
commandlet to expand them into a Shader Pipeline Cache (.spc file) for better
runtime performance.
"""

import glob
import logging
import os
import shutil
import subprocess
import sys

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# The REC files live in the Saved folder of the Staging Build
REC_DIR = os.path.join(
    config.STAGING_DIR, 'Windows', config.PROJECT_NAME, 'Saved',
    'CollectedPSOs'
)
# The SHK files live in the Saved/Cooked folder of the Project
SHK_SOURCE = os.path.join(
    config.PROJECT_ROOT, 'Saved', 'Cooked', 'Windows', config.PROJECT_NAME,
    'Metadata', 'PipelineCaches'
)
# Temporary output location (inside the Staging Content for safety)
TEMP_OUTPUT = os.path.join(
    config.STAGING_DIR, 'Windows', config.PROJECT_NAME, 'Content',
    'PipelineCaches', f'{config.PROJECT_NAME}_PCD3D_SM6.spc'
)
# Final Storage
HARD_STORAGE = os.path.join(
    config.PSO_CACHE_DIR, f'{config.PROJECT_NAME}_PCD3D_SM6.spc'
)
LOG_FILE = os.path.join(config.LOG_DIR, 'ShaderBuild.log')


def main():
    """Compiles recorded PSOs into a shader pipeline cache."""
    logger.info('Scanning for RECs in: %s', REC_DIR)
    rec_files = glob.glob(os.path.join(REC_DIR, '*.rec*'))
    if not rec_files:
        logger.error('[ERROR] No .rec files found. Did Step 2 run?')
        sys.exit(1)

    logger.info('Found %d recordings.', len(rec_files))

    cmd = [
        config.EDITOR_CMD,
        config.UPROJECT_PATH,
        '-run=ShaderPipelineCacheTools',
        '-unattended',
        '-nopause',
        '-NoLiveCoding',
        '-dpcvars="LiveCoding.Enable=0"',
        'expand',
        os.path.join(REC_DIR, '*.rec*'),
        os.path.join(SHK_SOURCE, '*SM6.shk'),
        TEMP_OUTPUT
    ]

    with open(LOG_FILE, 'w', encoding='utf-8') as log:
        subprocess.run(
            cmd, stdout=log, stderr=subprocess.STDOUT, check=False
        )

    if os.path.exists(TEMP_OUTPUT):
        os.makedirs(os.path.dirname(HARD_STORAGE), exist_ok=True)
        shutil.copy2(TEMP_OUTPUT, HARD_STORAGE)
        logger.info('[SUCCESS] Cache Saved to: %s', HARD_STORAGE)
    else:
        logger.error('[ERROR] Cache generation failed. Check log: %s', LOG_FILE)
        sys.exit(1)


if __name__ == '__main__':
    main()