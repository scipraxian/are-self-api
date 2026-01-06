"""Production build script for the UE project using UAT.

This script executes a full BuildCookRun command with archiving enabled,
cleaning previous builds and rescuing the UAT log upon completion.
"""

import logging
import os
import shutil
import subprocess
import sys

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

LOG_DEST = os.path.join(config.LOG_DIR, 'UATBuild.log')


def get_uat_log_source():
    """Finds the default UAT log in AppData.

    Returns:
        str: The absolute path to the UAT log file.
    """
    appdata = os.getenv('APPDATA')
    if not appdata:
        return ''
    # The folder name is often the engine installation path hashed/sanitized
    log_dir_name = 'C+Program+Files+Epic+Games+UE_5.6'
    return os.path.join(
        appdata, 'Unreal Engine', 'AutomationTool', 'Logs', log_dir_name,
        'Log.txt'
    )


def main():
    """Cleans the build directory and runs the production build."""
    print('=' * 49)
    print(' STEP 4: UAT PRODUCTION BUILD (Robust)')
    print('=' * 49)

    # 1. Clean
    windows_arch = os.path.join(config.BUILD_ROOT, 'Windows')
    if os.path.exists(windows_arch):
        try:
            shutil.rmtree(windows_arch)
        except Exception:  # pylint: disable=broad-except
            pass

    # 2. Build Arguments
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
        '-archive',
        f'-archivedirectory={config.BUILD_ROOT}',
        '-unversionedcookedcontent',
        '-zenstore',
        '-compressed',
        '-nocompileeditor',
        '-utf8output',
        '-nopause'
    ]

    logger.info('Building... (Check this window for progress)')

    try:
        # shell=True is needed for running UAT.bat
        result = subprocess.run(cmd, shell=True, check=False)
        if result.returncode != 0:
            logger.error('\n[ERROR] Build failed with code %s', result.returncode)
            sys.exit(result.returncode)

    except KeyboardInterrupt:
        logger.warning('\n[ABORTED] User cancelled build.')
        sys.exit(1)

    finally:
        # 3. Always Capture Log
        logger.info('\n[Log] Rescuing UAT Log...')
        src = get_uat_log_source()
        if src and os.path.exists(src):
            try:
                shutil.copy2(src, LOG_DEST)
                logger.info('   Saved to: %s', LOG_DEST)
            except Exception as e:  # pylint: disable=broad-except
                logger.error('   [Error] Could not copy log: %s', e)
        else:
            logger.warning('   [Warning] Log not found at %s', src)


if __name__ == '__main__':
    main()