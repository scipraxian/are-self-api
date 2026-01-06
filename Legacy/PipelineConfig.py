"""Configuration pipeline for the Builder for UE.

This module loads the configuration from builder_config.json and exposes
constants for use throughout the pipeline.
"""

import json
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- CONSTANTS ---
CONFIG_FILENAME = 'builder_config.json'
TEMPLATE_FILENAME = 'builder_config.template.json'

# Helper to find the config file relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, CONFIG_FILENAME)


def load_config():
    """Loads and validates the configuration from the JSON file.

    Returns:
        dict: The loaded configuration data.

    Raises:
        SystemExit: If the configuration file is missing or invalid.
    """
    if not os.path.exists(CONFIG_PATH):
        logger.critical(
            'Configuration file not found: %s', CONFIG_PATH
        )
        logger.info(
            "Please copy '%s' to '%s' and configure your paths.",
            TEMPLATE_FILENAME,
            CONFIG_FILENAME
        )
        sys.exit(1)

    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.critical('Invalid JSON in %s:\n%s', CONFIG_FILENAME, e)
        sys.exit(1)

    # Required Keys Validation
    required_keys = [
        'ProjectName', 'ProjectRoot', 'EngineRoot', 'BuildRoot', 'StagingDir'
    ]
    missing_keys = [key for key in required_keys if key not in data]

    if missing_keys:
        logger.critical('Missing required keys in %s:', CONFIG_FILENAME)
        for key in missing_keys:
            logger.error('  - %s', key)
        sys.exit(1)

    return data


# --- LOAD DATA ---
_DATA = load_config()

# --- EXPOSE CONSTANTS ---
PROJECT_NAME = _DATA['ProjectName']
PROJECT_ROOT = _DATA['ProjectRoot']
ENGINE_ROOT = _DATA['EngineRoot']
BUILD_ROOT = _DATA['BuildRoot']
STAGING_DIR = _DATA['StagingDir']
AGENT_PORT = _DATA.get('AgentPort', 5005)

# --- DIRECTORY STRUCTURE ---
BUILDER_DIR = SCRIPT_DIR
LOG_DIR = os.path.join(BUILDER_DIR, 'Logs')
# Path for the async status file
STATUS_FILE = os.path.join(BUILDER_DIR, 'agent_status.json')

# --- DERIVED CONSTANTS (Auto-Calculated) ---
UPROJECT_PATH = os.path.join(PROJECT_ROOT, f'{PROJECT_NAME}.uproject')
BUILD_BAT = os.path.join(
    ENGINE_ROOT, 'Engine', 'Build', 'BatchFiles', 'Build.bat'
)
UAT_BATCH = os.path.join(
    ENGINE_ROOT, 'Engine', 'Build', 'BatchFiles', 'RunUAT.bat'
)
EDITOR_CMD = os.path.join(
    ENGINE_ROOT, 'Engine', 'Binaries', 'Win64', 'UnrealEditor-Cmd.exe'
)
UBT_EXE = os.path.join(
    ENGINE_ROOT, 'Engine', 'Binaries', 'DotNET', 'UnrealBuildTool',
    'UnrealBuildTool.exe'
)

# --- RELEASE / STAGE PATHS ---
RELEASE_TEST_DIR = os.path.join(BUILD_ROOT, 'ReleaseTest')
PSO_CACHE_DIR = os.path.join(
    PROJECT_ROOT, PROJECT_NAME, 'Build', 'Windows', 'PipelineCaches'
)

# --- REMOTE TARGETS PROCESSING ---
_RAW_TARGETS = _DATA.get('RemoteTargets', [])
REMOTE_TARGETS = []

for t in _RAW_TARGETS:
    target_entry = t.copy()

    # 1. Ensure 'agent_port' exists (Default to global AGENT_PORT if missing)
    if 'agent_port' not in target_entry:
        target_entry['agent_port'] = AGENT_PORT

    # 2. Ensure 'path' is treated as UNC
    # (JSON already has correct paths, this is just pass-through)

    REMOTE_TARGETS.append(target_entry)