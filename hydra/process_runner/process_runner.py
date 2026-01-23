import asyncio
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class AsyncProcessRunner(object):
    """
    Manages the lifecycle of a subprocess and streams its STDOUT/STDERR.
    """

    def __init__(self, command: list, cwd: str = None):
        self.command = command
        self.cwd = cwd
        self.process = None

    async def start(self):
        """Launches the process asynchronously."""
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                cwd=self.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
                limit=1024 * 128,  # 128KB buffer
            )
            logger.info(f'Process started. PID: {self.process.pid}')
        except Exception as e:
            logger.error(f'Failed to start process: {e}')
            raise

    async def stream_output(self) -> AsyncGenerator[str, None]:
        """
        Yields lines from stdout as they arrive.
        Stops automatically when process exits and buffer is empty.
        """
        if not self.process:
            raise RuntimeError('Process not started. Call start() first.')

        async for line in self.process.stdout:
            if line:
                yield line.decode('utf-8', errors='replace')

    async def wait(self):
        """Waits for the process to exit and returns exit code."""
        if self.process:
            return await self.process.wait()
        return None

    @property
    def is_running(self):
        return self.process and self.process.returncode is None
