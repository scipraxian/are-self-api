"""Utility functions for communicating with remote agents and rescuing logs.

This module provides functions to send commands to remote agents via TCP
and to copy log files from remote machines to the local log directory.
"""

import logging
import os
import shutil
import socket
import subprocess

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)


def send_agent_command(host, command, timeout=15):
    """Sends a command (KILL/LAUNCH/PING) to the remote agent.

    Args:
        host (str): The hostname or IP address of the remote agent.
        command (str): The command to send.
        timeout (int): The connection timeout in seconds.

    Returns:
        bool: True if the command was successful and returned the expected
            response, False otherwise.
    """
    logger.info(
        '   [AGENT] Connecting to %s:%s -> %s...',
        host, config.AGENT_PORT, command
    )
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, config.AGENT_PORT))
            s.sendall(command.encode('utf-8'))

            data = s.recv(1024).decode('utf-8')
            logger.info('   [AGENT] Response: %s', data)

            if command == 'KILL' and data == 'KILLED':
                return True
            if command == 'LAUNCH' and data == 'LAUNCHED':
                return True
            if command == 'PING' and data == 'PONG':
                return True

    except socket.timeout:
        logger.warning('   [AGENT] Request Timed Out. Is the Agent running?')
    except ConnectionRefusedError:
        logger.warning('   [AGENT] Connection Refused. Agent not active on target.')
    except Exception as e:
        logger.exception('   [AGENT] Error: %s', e)

    return False


def rescue_remote_log(target_dict):
    """Copies the game log from the remote machine to the local builder logs.

    Args:
        target_dict (dict): A dictionary containing target 'name' and UNC 'path'.
    """
    name = target_dict['name']
    unc_path = target_dict['path']

    logger.info('   [LOGS] Fetching log from %s...', name)

    # Path construction assumes standard layout on remote
    remote_log = os.path.join(
        unc_path, 'ReleaseTest', config.PROJECT_NAME, 'Saved', 'Logs',
        f'{config.PROJECT_NAME}.log'
    )
    dest_filename = f'{name}_Agent.log'
    local_dest = os.path.join(config.LOG_DIR, dest_filename)

    if os.path.exists(remote_log):
        try:
            if not os.path.exists(config.LOG_DIR):
                os.makedirs(config.LOG_DIR)

            try:
                shutil.copy2(remote_log, local_dest)
                logger.info('   [LOGS] Success! Saved to: %s', local_dest)
            except PermissionError:
                logger.info(
                    '   [LOGS] File locked. Attempting Shadow Copy (Robocopy fallback)...'
                )
                subprocess.run(
                    [
                        'robocopy',
                        os.path.dirname(remote_log),
                        config.LOG_DIR,
                        f'{config.PROJECT_NAME}.log',
                        '/R:1',
                        '/W:1',
                        '/NJH',
                        '/NJS',
                        '/NFL',
                        '/NDL'
                    ],
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False
                )
                temp_dest = os.path.join(config.LOG_DIR, f'{config.PROJECT_NAME}.log')
                if os.path.exists(temp_dest):
                    if os.path.exists(local_dest):
                        os.remove(local_dest)
                    os.rename(temp_dest, local_dest)
                    logger.info('   [LOGS] Success (Robocopy)! Saved to: %s', local_dest)
                else:
                    logger.error('   [LOGS] Failed to copy locked file.')

        except Exception as e:
            logger.exception('   [LOGS] Failed to copy log: %s', e)
    else:
        logger.warning('   [LOGS] Warning: Log not found at %s', remote_log)


# Re-export targets for easy access by other scripts
TARGETS = config.REMOTE_TARGETS