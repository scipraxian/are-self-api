"""Staging build script for the UE project.

This script executes the Unreal Automation Tool (UAT) BuildCookRun command
to build and stage the project for iterative testing and PSO recording.
"""

import logging
import os
import subprocess
import sys

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)


def main():
    """Executes the staging build process using UAT."""
    print('=' * 49)
    print(' STEP 1: STAGING BUILD (Live Feed)')
    print('=' * 49)
    print(f'Target: {config.STAGING_DIR}')

    # Ensure log dir exists
    log_file = os.path.join(config.LOG_DIR, 'StagingBuild.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    cmd = [
        config.UAT_BATCH,
        'BuildCookRun',
        f'-project={config.UPROJECT_PATH}',
        '-platform=Win64',
        '-clientconfig=Development',
        '-serverconfig=Development',
        '-build',
        '-cook',
        '-stage',
        '-pak',
        f'-stagingdirectory={config.STAGING_DIR}',
        '-nocompileeditor',
        '-unattended',
        '-nopause',
        '-utf8output'
    ]

    logger.info('[Exec] Starting UAT... (Output will stream below)')
    print('-' * 60)

    try:
        with open(log_file, 'w', encoding='utf-8') as log_f:
            # shell=True is often needed for batch files on Windows cmd
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                shell=True
            )

            # process.stdout is strictly Iter[str] here due to universal_newlines
            if process.stdout:
                for line in process.stdout:
                    sys.stdout.write(line)
                    log_f.write(line)
                    sys.stdout.flush()
                    log_f.flush()

            return_code = process.wait()

        print('-' * 60)

        if return_code != 0:
            logger.error('[ERROR] Staging Build Failed. Code: %s', return_code)
            logger.info('        Log saved to: %s', log_file)
            sys.exit(return_code)

        logger.info('[SUCCESS] Staging Build Complete.')
    except Exception as e:  # pylint: disable=broad-except
        logger.exception('An unexpected error occurred during staging: %s', e)
        sys.exit(1)


if __name__ == '__main__':
    main()