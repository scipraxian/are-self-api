"""Parallel build distribution script for the UE project.

This script uses multi-threading to simultaneously distribute builds to multiple
remote targets using robocopy, preserving user data by excluding the Saved
directory, and optionally launching the game via remote agents.
"""

import concurrent.futures
import json
import logging
import os
import subprocess
import time
from typing import Any, Dict

import AgentUtils
import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)


class ParallelDistributor:
    """Manages multi-threaded file distribution to remote targets."""

    def __init__(self):
        """Initializes the ParallelDistributor with source and status paths."""
        self._source_dir = os.path.join(config.BUILD_ROOT, 'ReleaseTest')
        self._status_file = config.STATUS_FILE

    def _load_status(self) -> Dict[str, Any]:
        """Loads the current agent status cache from the status file.

        Returns:
            Dict[str, Any]: The loaded status mapping.
        """
        if not os.path.exists(self._status_file):
            return {}
        try:
            with open(self._status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:  # pylint: disable=broad-except
            return {}

    def _run_robocopy(self, dest_path: str) -> bool:
        """Executes robocopy to mirror the build, excluding user data.

        Args:
            dest_path (str): The root destination path on the remote target.

        Returns:
            bool: True if the copy was successful (robocopy exit code < 8).
        """
        destination = os.path.join(dest_path, 'ReleaseTest')

        # /MIR : Mirror (Copy new, delete extra)
        # /XD "Saved" : EXCLUDE DIRECTORY "Saved".
        # /R:2 /W:2 : Retry 2 times, wait 2 sec
        # /NFL /NDL : Silent file listing
        cmd = [
            'robocopy',
            self._source_dir,
            destination,
            '/MIR',
            '/XD', 'Saved',  # Protects remote user data.
            '/R:2', '/W:2',
            '/NFL', '/NDL', '/NJH', '/NJS'
        ]

        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False
        )
        return result.returncode < 8

    def _process_target(
        self, target: Dict[str, Any], status: Dict[str, Any]
    ) -> str:
        """Handles copy and optional launch for a single target.

        Args:
            target (Dict[str, Any]): Target configuration dictionary.
            status (Dict[str, Any]): Current status for this target.

        Returns:
            str: A message summarizing the result for this target.
        """
        name = target['name']
        dest = target['path']

        # 1. Validation
        if not status.get('share_ok', False):
            return f'[{name}] SKIPPED (Share Unavailable)'

        logger.info('[%s] Starting Copy -> %s ...', name, dest)

        # 2. Copy
        start_t = time.time()
        success = self._run_robocopy(dest)
        duration = time.time() - start_t

        if not success:
            return f'[{name}] COPY FAILED'

        msg = f'[{name}] COPY COMPLETE ({duration:.1f}s)'

        # 3. Launch
        if status.get('agent_ok', False):
            logger.info('[%s] Sending LAUNCH command...', name)
            if AgentUtils.send_agent_command(name, 'LAUNCH'):
                msg += ' + LAUNCHED'
            else:
                msg += ' + LAUNCH FAIL'
        else:
            msg += ' (No Agent - Copy Only)'

        return msg

    def run(self):
        """Executes the parallel distribution across all configured targets."""
        print('=' * 49)
        print('   PARALLEL DISTRIBUTION (Async v5.1 Safe)')
        print('=' * 49)

        status_map = self._load_status()
        if not status_map:
            logger.error('[ERROR] No status data found. Is AgentMonitor running?')
            input('Press Enter...')
            return

        futures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for target in config.REMOTE_TARGETS:
                name = target['name']
                t_status = status_map.get(name, {})
                futures.append(
                    executor.submit(self._process_target, target, t_status)
                )

            for future in concurrent.futures.as_completed(futures):
                logger.info('   > %s', future.result())

        logger.info('\n[DONE] Distribution Cycle Complete.')
        time.sleep(2)


if __name__ == '__main__':
    distributor = ParallelDistributor()
    distributor.run()