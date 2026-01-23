import asyncio
import logging
import os

from watchfiles import awatch

# Suppress "1 change detected" log spam from the file watcher
logging.getLogger('watchfiles').setLevel(logging.WARNING)


class AsyncLogMonitor:
    def __init__(self, file_path: str, launch_time: float = 0.0):
        self.file_path = file_path
        self.launch_time = launch_time

        # Internal state
        self._queue = asyncio.Queue()
        self._watcher_task = None
        self._current_offset = 0
        self._stop_event = asyncio.Event()

    async def start(self):
        """Starts the background file watcher."""
        if not self._watcher_task:
            self._watcher_task = asyncio.create_task(self._watch_loop())

    async def stop(self):
        """Stops the background watcher."""
        self._stop_event.set()
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

    async def check_for_lines(self):
        """
        Non-blocking consumer. Drains the queue of any lines
        collected by the background watcher.
        """
        # Lazy start to ensure the loop is running
        if not self._watcher_task:
            await self.start()

        lines = []
        try:
            while True:
                lines.append(self._queue.get_nowait())
        except asyncio.QueueEmpty:
            pass
        return lines

    async def _watch_loop(self):
        """
        Background Producer:
        1. Watches directory for changes using OS signals (watchfiles).
        2. Reads new content on change.
        3. Pushes lines to the queue.
        """
        # 1. Initial Read (Catch up if file already exists)
        self._read_file()

        # 2. Determine directory to watch
        directory = os.path.dirname(self.file_path)
        if not directory:
            directory = '.'

        # 3. Watch Loop
        try:
            async for changes in awatch(directory, stop_event=self._stop_event):
                for change_type, path in changes:
                    # Filter for our specific log file
                    if os.path.abspath(path) == os.path.abspath(self.file_path):
                        self._read_file()
        except asyncio.CancelledError:
            pass
        except Exception:
            # Fallback/Recovery could go here, but for now we exit
            pass

    def _read_file(self):
        """Manual read logic handling offsets, rotation, and UTF-8."""
        if not os.path.exists(self.file_path):
            return

        # Stale file check
        try:
            if os.path.getmtime(self.file_path) < self.launch_time:
                return
        except OSError:
            return

        try:
            with open(
                self.file_path, 'r', encoding='utf-8', errors='replace'
            ) as f:
                # Handle Truncation (Log rotation or restart)
                f.seek(0, os.SEEK_END)
                file_size = f.tell()

                if file_size < self._current_offset:
                    self._current_offset = 0

                # Seek to last read position
                f.seek(self._current_offset)

                # Read new lines
                for line in f:
                    self._queue.put_nowait(line)

                self._current_offset = f.tell()

        except Exception:
            # File locking issues (common on Windows) or permissions.
            # We ignore and retry on the next 'change' event.
            pass
