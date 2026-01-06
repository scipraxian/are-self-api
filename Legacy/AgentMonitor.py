"""Background daemon to monitor availability of remote build targets.

This module pings remote targets and checks for open ports and accessible
network shares, updating a status file periodically.
"""

import json
import logging
import os
import socket
import subprocess
import time

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)


class StatusMonitor:
    """Background daemon to monitor availability of remote build targets."""

    @staticmethod
    def _check_ping(host: str) -> bool:
        """Checks if the host responds to ICMP ping.

        Args:
            host (str): The hostname or IP address to ping.

        Returns:
            bool: True if the host is reachable, False otherwise.
        """
        try:
            output = subprocess.run(
                ['ping', '-n', '1', '-w', '500', host],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
            return output.returncode == 0
        except Exception:  # pylint: disable=broad-except
            return False

    @staticmethod
    def _check_port(host: str, port: int) -> bool:
        """Checks if a TCP port is open on the host.

        Args:
            host (str): The hostname or IP address.
            port (int): The port number to check.

        Returns:
            bool: True if the port is open, False otherwise.
        """
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except Exception:  # pylint: disable=broad-except
            return False

    @staticmethod
    def _check_share(unc_path: str) -> bool:
        """Checks if a network UNC path is accessible.

        Args:
            unc_path (str): The UNC path to check.

        Returns:
            bool: True if the path exists/is accessible, False otherwise.
        """
        return os.path.exists(unc_path)

    def run(self):
        """Main monitoring loop. Runs indefinitely until interrupted."""
        # Daemon mode - no logger.info statements to avoid log spamming
        # unless necessary.
        while True:
            status_data = {}
            timestamp = time.strftime('%H:%M:%S')

            for target in config.REMOTE_TARGETS:
                name = target['name']

                # 1. Ping (Fast Fail)
                is_alive = self._check_ping(name)

                # 2. Share (Distribution Dependency)
                is_share_ok = False
                if is_alive:
                    is_share_ok = self._check_share(target['path'])

                # 3. Agent (Control Dependency)
                is_agent_ok = False
                if is_alive:
                    is_agent_ok = self._check_port(name, target['agent_port'])

                status_data[name] = {
                    'last_seen': timestamp,
                    'online': is_alive,
                    'share_ok': is_share_ok,
                    'agent_ok': is_agent_ok
                }

            # Atomic Write
            temp_file = config.STATUS_FILE + '.tmp'
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(status_data, f, indent=4)
                os.replace(temp_file, config.STATUS_FILE)
            except Exception:  # pylint: disable=broad-except
                pass

            time.sleep(3)


def monitor_loop():
    """Wrapper function to instantiate and run the StatusMonitor."""
    monitor = StatusMonitor()
    monitor.run()


if __name__ == '__main__':
    monitor_loop()