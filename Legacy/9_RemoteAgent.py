"""Remote game agent server for process control and status monitoring.

This script runs on a target machine, listening for TCP commands to kill,
launch, or ping the game process. It provides graceful and forceful termination
logic and handles project-specific configurations.
"""

import json
import logging
import os
import socket
import subprocess
import time
from typing import Any, Dict

import psutil

# Configure logging
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
CONFIG_FILE = 'builder_config.json'
DEFAULT_PING_INTERVAL = 60.0

DEFAULT_CONFIG = {
    'ProjectName': 'HSHVacancy',
    'BuildRoot': r'C:\steambuild',
    'AgentPort': 5005
}


class RemoteAgentServer:
    """Manages the remote game agent and process control.

    Attributes:
        _config: A dictionary containing project configuration.
        _last_ping_time: Timestamp of the last logged PING request.
        _port: The port to listen on.
        _project_name: The name of the Unreal project.
        _process_name: The name of the game executable process.
        _game_exe_path: The full path to the game executable.
    """

    def __init__(self):
        """Initializes the RemoteAgentServer with configuration and paths."""
        self._config = self._load_config()
        self._last_ping_time = 0.0
        self._port = self._config.get('AgentPort', 5005)

        self._project_name = self._config.get('ProjectName', 'HSHVacancy')
        self._process_name = f'{self._project_name}.exe'
        build_root = self._config.get('BuildRoot', r'C:\steambuild')
        self._game_exe_path = os.path.join(
            build_root, 'ReleaseTest', self._process_name
        )

    def _load_config(self) -> Dict[str, Any]:
        """Loads configuration from JSON or returns defaults.

        Returns:
            Dict[str, Any]: The loaded configuration data.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, CONFIG_FILE)

        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:  # pylint: disable=broad-except
                logger.error('[ERROR] Could not read %s: %s', CONFIG_FILE, e)
        return DEFAULT_CONFIG

    def _is_game_running(self) -> bool:
        """Checks if the game process is currently active.

        Returns:
            bool: True if the process exists, False otherwise.
        """
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == self._process_name:
                return True
        return False

    def _kill_game(self) -> str:
        """Terminates the game process gracefully, then forcefully if needed.

        Returns:
            str: 'KILLED' if successful.
        """
        logger.info(
            '[AGENT] Requesting Graceful Exit for %s...', self._process_name
        )
        subprocess.run(
            f'taskkill /IM {self._process_name}',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )

        logger.info('   > Waiting for shutdown')
        for _ in range(10):
            if not self._is_game_running():
                logger.info('   > Application closed successfully.')
                return 'KILLED'
            time.sleep(1)

        logger.warning('   [!] Graceful exit timed out. FORCE KILLING.')

        killed_any = False
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == self._process_name:
                try:
                    proc.kill()
                    logger.info('   > Terminated PID: %s', proc.info['pid'])
                    killed_any = True
                except psutil.NoSuchProcess:
                    pass

        if killed_any:
            os.system(f'taskkill /f /im {self._process_name} >nul 2>&1')

        return 'KILLED'

    def _launch_game(self) -> str:
        """Launches the game executable with auto-start flags.

        Returns:
            str: 'LAUNCHED' if successful, or an error code.
        """
        logger.info(
            '[AGENT] Launching %s with -AutoStart...', self._game_exe_path
        )
        if not os.path.exists(self._game_exe_path):
            logger.error('   [ERROR] File not found: %s', self._game_exe_path)
            return 'ERROR_NO_EXE'

        try:
            subprocess.Popen(
                [
                    self._game_exe_path, '-AutoStart', '-log', '-windowed',
                    '-resX=1280', '-resY=720'
                ],
                creationflags=(
                    subprocess.DETACHED_PROCESS |
                    subprocess.CREATE_NEW_PROCESS_GROUP
                )
            )
            return 'LAUNCHED'
        except Exception as e:  # pylint: disable=broad-except
            logger.error('   [ERROR] Launch failed: %s', e)
            return 'ERROR_LAUNCH_FAILED'

    def _handle_command(self, cmd: str, addr_ip: str) -> str:
        """Processes a received command string and returns the response.

        Args:
            cmd (str): The command string (PING/KILL/LAUNCH).
            addr_ip (str): The IP address of the sender.

        Returns:
            str: The response string (PONG/KILLED/LAUNCHED/etc).
        """
        if cmd == 'PING':
            current_time = time.time()
            if current_time - self._last_ping_time > DEFAULT_PING_INTERVAL:
                logger.info('[PING] Heartbeat from %s', addr_ip)
                self._last_ping_time = current_time
            return 'PONG'

        logger.info('[CMD] Received: %s from %s', cmd, addr_ip)

        if cmd == 'KILL':
            return self._kill_game()
        if cmd == 'LAUNCH':
            return self._launch_game()

        return 'UNKNOWN_CMD'

    def run(self):
        """Starts the server loop, listening for incoming TCP connections."""
        host = '0.0.0.0'
        print(f'--- HSH REMOTE AGENT ONLINE ({host}:{self._port}) ---')
        print(f'Target:  {self._game_exe_path}')

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, self._port))
            s.listen()

            while True:
                try:
                    conn, addr = s.accept()
                    with conn:
                        data = conn.recv(1024).decode('utf-8').strip()
                        if not data:
                            continue

                        response = self._handle_command(data, addr[0])
                        conn.sendall(response.encode('utf-8'))
                except Exception as e:  # pylint: disable=broad-except
                    logger.error('Connection Error: %s', e)


if __name__ == '__main__':
    agent = RemoteAgentServer()
    agent.run()