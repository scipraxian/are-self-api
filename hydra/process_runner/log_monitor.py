import asyncio
import logging
import os
import time

from watchfiles import awatch

# Suppress "1 change detected" log spam
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
        self._file_found = False  # Track if we ever successfully read the file

    async def start(self):
        """Starts the background file watcher."""
        if not self._watcher_task:
            self._watcher_task = asyncio.create_task(self._watch_loop())

    async def stop(self):
        """Stops the background watcher and reports if file was missing."""
        self._stop_event.set()
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

        # Final Report: Did we ever see the file?
        if not self._file_found:
            self._queue.put_nowait(
                f"\n[MONITOR] Info: Log file '{self.file_path}' never appeared during execution.\n"
            )

    async def check_for_lines(self):
        """
        Non-blocking consumer. Drains the queue.
        """
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
        Background Producer: Waits for Folder -> Watches Folder -> Reads File.
        """
        # 1. Determine directory to watch
        directory = os.path.dirname(self.file_path)
        if not directory:
            directory = '.'

        # 2. PATIENCE PHASE: Wait for directory to appear
        # We try for 10 seconds, checking every 1s.
        wait_start = time.time()
        dir_exists = False
        while time.time() - wait_start < 10.0:
            if os.path.exists(directory):
                dir_exists = True
                break
            if self._stop_event.is_set():
                return
            await asyncio.sleep(1.0)

        if not dir_exists:
            # Folder never showed up. We exit the watcher, but we don't crash.
            # The stop() method will handle the "never appeared" log.
            return

        # 3. INITIAL READ: Catch up if file already exists
        self._read_file()

        # 4. WATCH PHASE: Event-driven monitoring
        try:
            async for changes in awatch(directory, stop_event=self._stop_event):
                for change_type, path in changes:
                    if os.path.abspath(path) == os.path.abspath(self.file_path):
                        self._read_file()
        except asyncio.CancelledError:
            pass
        except Exception:
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
                self._file_found = True  # Mark success

        except Exception:
            pass
