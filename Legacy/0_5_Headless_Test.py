"""Headless Gatekeeper Script for running UE unit tests.

This script compiles the project editor and runs automation tests in headless
mode, parsing the resulting JSON report into a human-readable summary.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from typing import List

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

# --- Constants ---
LOG_SOURCE_DIR = os.path.join(config.PROJECT_ROOT, 'Saved', 'Logs')
REPORT_FILENAME = 'index.json'
SUMMARY_FILENAME = 'HeadlessTest_Summary.txt'
LOG_FILENAME = 'HeadlessTest.log'
TEST_PREFIX = 'HSH.Tests.Core.Statements'  # Adjust if your tests change


def run_command(args: List[str], error_message: str) -> None:
    """Runs a shell command and exits on failure.

    Args:
        args (List[str]): The command and its arguments.
        error_message (str): The message to display if the command fails.
    """
    try:
        # Note: shell=True is used here as UBT requires it for certain env setups
        subprocess.run(args, check=True, shell=True)
    except subprocess.CalledProcessError:
        logger.error('ERROR: %s', error_message)
        sys.exit(1)


def format_test_name(full_path: str, display_name: str) -> str:
    """Formats the test name for the summary report.

    Args:
        full_path (str): The full automation test path.
        display_name (str): The display name of the test.

    Returns:
        str: A formatted string containing context and display name.
    """
    if full_path.startswith(TEST_PREFIX):
        remainder = full_path[len(TEST_PREFIX):].strip('.')
        parts = remainder.split('.')
        if len(parts) >= 2:
            context = parts[0]
            return f'{context} | {display_name}'
    return display_name


def parse_test_report() -> None:
    """Parses the automation test JSON report and writes a summary."""
    json_path = os.path.join(config.LOG_DIR, REPORT_FILENAME)
    summary_path = os.path.join(config.LOG_DIR, SUMMARY_FILENAME)

    logger.info('[3/4] Parsing Test Report from %s...', json_path)

    if not os.path.exists(json_path):
        logger.warning('WARNING: No JSON report found.')
        return

    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except Exception as e:  # pylint: disable=broad-except
        logger.error('ERROR: %s', e)
        return

    output_lines = [
        '=' * 49,
        f' TEST RESULTS SUMMARY: {config.PROJECT_NAME}',
        '=' * 49,
        f'{"TEST CONTEXT | NAME":<70} | {"STATUS":<10} | {"TIME (s)":<10}',
        '-' * 95
    ]

    tests = data.get('tests', [])
    passed = 0
    failed = 0

    for test in tests:
        full_path = test.get('fullTestPath', '')
        display_name = test.get('testDisplayName', 'Unknown')
        state = test.get('state', 'Unknown')
        duration = test.get('duration', 0.0)

        formatted_name = format_test_name(full_path, display_name)
        status_str = 'PASS' if state == 'Success' else 'FAIL'

        if state == 'Success':
            passed += 1
        else:
            failed += 1

        output_lines.append(
            f'{formatted_name:<70} | {status_str:<10} | {duration:.4f}'
        )

        if state != 'Success':
            entries = test.get('entries', [])
            for entry in entries:
                event = entry.get('event')
                if isinstance(event, dict) and event.get('type') == 'Error':
                    msg = event.get('message', 'No message provided')
                    output_lines.append(f'    >>> ERROR: {msg}')

    output_lines.append('-' * 95)
    output_lines.append(
        f'TOTAL: {len(tests)}  |  PASSED: {passed}  |  FAILED: {failed}'
    )
    output_lines.append('=' * 49)

    try:
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        logger.info('Summary saved to: %s', summary_path)
        print('\n' + '\n'.join(output_lines))
    except OSError as e:
        logger.error('ERROR: Could not write summary: %s', e)


def archive_log() -> None:
    """Archives the project log file to the local logs directory."""
    logger.info('[4/4] Archiving Logs...')
    if not os.path.exists(config.LOG_DIR):
        os.makedirs(config.LOG_DIR)

    source_log = os.path.join(LOG_SOURCE_DIR, f'{config.PROJECT_NAME}.log')
    dest_log = os.path.join(config.LOG_DIR, LOG_FILENAME)

    if os.path.exists(source_log):
        try:
            shutil.copy2(source_log, dest_log)
            logger.info('Log saved: %s', dest_log)
        except OSError as e:
            logger.warning('WARNING: Failed to copy log file. %s', e)
    else:
        logger.warning('WARNING: Source log not found at %s', source_log)


def main() -> None:
    """Main execution point for Step 0.5."""
    print('=' * 49)
    print(' STEP 0.5: HEADLESS GATEKEEPER')
    print('=' * 49)

    if not os.path.exists(config.LOG_DIR):
        os.makedirs(config.LOG_DIR)

    logger.info('[1/2] Compiling %sEditor...', config.PROJECT_NAME)
    build_args = [
        config.BUILD_BAT,
        f'{config.PROJECT_NAME}Editor',
        'Win64',
        'Development',
        f'-Project={config.UPROJECT_PATH}',
        '-WaitMutex',
    ]
    run_command(build_args, 'Compilation Failed.')

    logger.info('[2/2] Running Unit Tests...')
    test_args = [
        config.EDITOR_CMD,
        config.UPROJECT_PATH,
        '-log',
        '-nullrhi',
        '-unattended',
        '-nopause',
        '-CustomConfig=Staging',
        f'-ReportExportPath={config.LOG_DIR}',
        '-ExecCmds=Automation RunTests HSH.Tests; Quit',
        '-TestExit=Automation Test Queue Empty',
    ]

    test_process = subprocess.run(test_args, capture_output=False, check=False)

    parse_test_report()
    archive_log()

    if test_process.returncode != 0:
        logger.error('ERROR: Unit Tests Failed.')
        sys.exit(1)

    logger.info('SUCCESS: Headless Gatekeeper Passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()