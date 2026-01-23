import asyncio
from os.path import exists, getmtime
from time import time

from pygtail import Pygtail


class AsyncLogMonitor(object):
    """
    Watches a log file for new entries using Pygtail for robust offset tracking.
    """

    def __init__(self, file_path: str):
        self._file_path = file_path
        self._tailer = None
        self._launch_time = time()

    async def check_for_lines(self) -> list:
        """
        Non-blocking call to read available new lines.
        Returns empty list if file doesn't exist yet or no new data.
        """
        loop = asyncio.get_running_loop()

        # Run the blocking I/O in a default thread executor
        # TODO: there are warnings already, handle exceptions etc.
        return await loop.run_in_executor(None, self._safe_read)

    def _safe_read(self):
        """Blocking helper method intended for the executor."""
        if not self._tailer:
            if not exists(self._file_path):
                return []
            if getmtime(self._file_path) < self._launch_time:
                return []
            try:
                self._tailer = Pygtail(
                    self._file_path,
                    full_lines=True,
                    paranoid=True,
                )
            except Exception:
                # TODO: expand, log, retry?
                return []
        return list(self._tailer)
