#!/usr/bin/env python3
"""Updates the application version JSON file with build metadata.

This script generates a unique hex hash based on the current timestamp,
captures the builder identity, and updates the target JSON file used
by the Unreal Engine runtime.
"""

import argparse
import datetime
import getpass
import json
import logging
import os
import sys
import time
from typing import Any, Dict

# Configure logging
logger = logging.getLogger(__name__)

_DEFAULT_INDENT = 4
_ENCODING = 'utf-8'


def _generate_build_metadata() -> Dict[str, Any]:
    """Generates the dynamic build metadata.

    Returns:
        Dict[str, Any]: A dictionary containing the calculated hash, date,
            day of year, and builder identity.
    """
    timestamp = int(time.time())
    hex_hash = hex(timestamp)[2:].upper()

    now = datetime.datetime.now()

    return {
        'Hash': hex_hash,
        'Date': now.strftime('%Y-%m-%d %H:%M:%S'),
        'DayOfYear': now.timetuple().tm_yday,
        'Builder': getpass.getuser(),
    }


def update_version_file(file_path: str) -> None:
    """Updates the specified JSON file with new build metadata.

    Preserves existing static version numbers (Major, Minor, Patch)
    while overwriting the 'Build' section.

    Args:
        file_path (str): The absolute or relative path to the AppVersion.json
            file.
    """
    logger.info('--- VERSION STAMPER ---')
    logger.info('Target: %s', file_path)

    # Validate directory existence to prevent "ghost" file creation.
    directory = os.path.dirname(os.path.abspath(file_path))
    if not os.path.exists(directory):
        try:
            os.makedirs(directory)
        except OSError as e:
            logger.error('[ERROR] Could not create directory %s: %s', directory, e)
            sys.exit(1)

    # Load existing data or initialize fresh structure.
    data: Dict[str, Any] = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding=_ENCODING) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            logger.warning('[WARNING] %s is corrupt. Re-initializing.', file_path)

    # Generate new data.
    build_meta = _generate_build_metadata()

    # Log to stdout for CI visibility.
    logger.info('  > Hash:    %s', build_meta['Hash'])
    logger.info('  > Date:    %s', build_meta['Date'])
    logger.info('  > Builder: %s', build_meta['Builder'])

    # Update logic: Preserve structure, inject 'Build' block.
    if 'Game' not in data:
        data['Game'] = {
            'Name': 'HSH: Vacancy',
            'Major': 0, 'Minor': 0, 'Patch': 0, 'Label': 'DEV'
        }

    # Overwrite the Build block entirely to ensure freshness.
    data['Build'] = build_meta

    if 'Target' not in data:
        data['Target'] = {'Environment': 'Production', 'Store': 'Steam'}

    # Write back to disk atomically (or close enough for this context).
    try:
        with open(file_path, 'w', encoding=_ENCODING) as f:
            json.dump(data, f, indent=_DEFAULT_INDENT)
        logger.info('[SUCCESS] Version Stamp Applied.')
    except IOError as e:
        logger.error('[ERROR] Failed to write to %s: %s', file_path, e)
        sys.exit(1)


def main() -> None:
    """Main entry point for version stamping."""
    parser = argparse.ArgumentParser(description='Stamp build version info.')
    parser.add_argument(
        'file_path',
        type=str,
        help='Path to the AppVersion.json file.'
    )
    args = parser.parse_args()

    # Configure basic logging for the script
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )

    update_version_file(args.file_path)


if __name__ == '__main__':
    main()