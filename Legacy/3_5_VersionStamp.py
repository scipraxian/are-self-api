"""Version stamping script for the UE project.

This script updates a Version.json file in the project's Config directory with
build metadata, including the current timestamp, git hash, and machine name.
"""

import datetime
import json
import logging
import os
import subprocess

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

VERSION_FILE = os.path.join(config.PROJECT_ROOT, 'Config', 'Version.json')


def get_git_hash():
    """Retrieves the short git hash of the project repository.

    Returns:
        str: The short git hash if successful, otherwise 'NOGIT'.
    """
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=config.PROJECT_ROOT
        ).decode('ascii').strip()
    except Exception:  # pylint: disable=broad-except
        return 'NOGIT'


def main():
    """Updates the version file with current build metadata."""
    print('=' * 49)
    print(' STEP 3.5: VERSION STAMPING')
    print('=' * 49)

    data = {}
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            pass

    if 'Game' not in data:
        data['Game'] = {'Major': 0, 'Minor': 0, 'Patch': 0}

    build_meta = {
        'Date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'Hash': get_git_hash(),
        'Machine': os.environ.get('COMPUTERNAME', 'Unknown')
    }

    data['Build'] = build_meta

    with open(VERSION_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

    logger.info('[Stamp] Updated Version.json:')
    print(json.dumps(data, indent=4))


if __name__ == '__main__':
    main()