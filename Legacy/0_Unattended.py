"""Pipeline orchestrator for unattended builds of the UE project.

This module automates the execution of multiple build steps, including
headless tests, staging, recording PSOs, and LAN distribution.
"""

import argparse
import datetime
import glob
import logging
import os
import subprocess
import sys
import time

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
MASTER_LOG = os.path.join(config.LOG_DIR, 'Pipeline_Master.log')

# --- PIPELINE DEFINITIONS ---
STEPS = [
    {
        'id': 0.5,
        'label': 'Gatekeeper: Headless Unit Tests',
        'cmd': [sys.executable, '0_5_Headless_Test.py'],
        'type': 'python'
    },
    {
        'id': 1.0,
        'label': 'Staging: Build Game (Buffer)',
        'cmd': [sys.executable, '1_Staging_Build.py'],
        'type': 'python'
    },
    {
        'id': 2.0,
        'label': 'Staging: Record PSOs',
        'cmd': [sys.executable, '2_Stage_Run.py'],
        'type': 'python'
    },
    {
        'id': 3.0,
        'label': 'Cache: Compile & Store',
        'cmd': [sys.executable, '3_CacheShaders.py'],
        'type': 'python'
    },
    {
        'id': 3.5,
        'label': 'Version: Stamp Metadata',
        'cmd': [sys.executable, '3_5_VersionStamp.py'],
        'type': 'python'
    },
    {
        'id': 4.0,
        'label': 'UAT: Build Production',
        'cmd': [sys.executable, '4_UAT_Build.py'],
        'type': 'python'
    },
    {
        'id': 5.0,
        'label': 'UAT: Deploy & Verify',
        'cmd': [sys.executable, '5_UAT_Run.py'],
        'type': 'python'
    },
    {
        'id': 6.0,
        'label': 'Distribute: LAN Deployment',
        'cmd': [sys.executable, '6_Distribute.py'],
        'type': 'python',
        'optional': True
    }
]


def log_master(msg):
    """Logs a message to the console and the master log file.

    Args:
        msg (str): The message to log.
    """
    timestamp = datetime.datetime.now().strftime('[%H:%M:%S]')
    line = f'{timestamp} {msg}'
    print(line)
    try:
        with open(MASTER_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:  # pylint: disable=broad-except
        pass


def clean_logs():
    """Removes all log files in the logo directory except the master log."""
    if not os.path.exists(config.LOG_DIR):
        os.makedirs(config.LOG_DIR)
    log_files = glob.glob(os.path.join(config.LOG_DIR, '*.log'))
    for f in log_files:
        if os.path.abspath(f) != os.path.abspath(MASTER_LOG):
            try:
                os.remove(f)
            except Exception:  # pylint: disable=broad-except
                pass


def run_step(step_info):
    """Runs a single build step in a new console window.

    Args:
        step_info (dict): A dictionary containing step 'label' and 'cmd'.

    Returns:
        bool: True if the step completed successfully (exit code 0).
    """
    log_master(f'>>> STARTING: {step_info["label"]}')
    start_time = time.time()

    # Spawn new console window (Windows only)
    create_new_console = 0x00000010

    try:
        result = subprocess.run(
            step_info['cmd'],
            cwd=config.BUILDER_DIR,
            creationflags=create_new_console,
            check=False
        )

        duration = time.time() - start_time
        if result.returncode != 0:
            log_master(
                f'!!! FAILED: {step_info["label"]} (Code: {result.returncode})'
            )
            return False

        log_master(f'    COMPLETE: {step_info["label"]} ({duration:.1f}s)')
        return True
    except Exception as e:
        log_master(f'!!! EXCEPTION: {e}')
        return False


def main():
    """Main entry point for the pipeline orchestrator."""
    if not os.path.exists(config.LOG_DIR):
        os.makedirs(config.LOG_DIR)
    with open(MASTER_LOG, 'w', encoding='utf-8') as f:
        f.write('--- PIPELINE START ---\n')

    parser = argparse.ArgumentParser()
    parser.add_argument('--start-at', type=float, default=0.5)
    parser.add_argument('--clean-logs', action='store_true')
    parser.add_argument('--distribute', action='store_true')
    args = parser.parse_args()

    # Clear screen on Windows
    os.system('cls' if os.name == 'nt' else 'clear')
    print('=' * 49)
    print(f'  {config.PROJECT_NAME} - PIPELINE ORCHESTRATOR 2.3')
    print('=' * 49)

    if args.clean_logs:
        clean_logs()

    success = True
    for step in STEPS:
        if step['id'] < args.start_at:
            continue
        if step.get('optional') and not args.distribute:
            continue
        if not run_step(step):
            success = False
            break

    if not success:
        log_master('!!! PIPELINE STOPPED ON FAILURE !!!')
        print('\n' + '!' * 60)
        print('   FAILURE DETECTED. GENERATING CONTEXT LOG...')
        print('!' * 60)
        try:
            subprocess.run(
                [sys.executable, '6_5_FeedTheAI.py'],
                cwd=config.BUILDER_DIR,
                check=False
            )
        except Exception:  # pylint: disable=broad-except
            pass
        input('Press Enter to close...')
        sys.exit(1)

    log_master('--- PIPELINE SUCCESSFUL ---')
    try:
        subprocess.run(
            [sys.executable, '6_5_FeedTheAI.py'],
            cwd=config.BUILDER_DIR,
            check=False
        )
    except Exception:  # pylint: disable=broad-except
        pass
    print('\n[DONE] Pipeline Complete.')


if __name__ == '__main__':
    main()