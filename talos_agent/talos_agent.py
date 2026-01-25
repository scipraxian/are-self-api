import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from typing import AsyncGenerator, Awaitable, Callable, List, Optional

# watchfiles is the only non-standard library we require.
try:
    from watchfiles import awatch
except ImportError:
    print('FATAL: Missing dependencies. Run: pip install watchfiles psutil')
    sys.exit(1)

# Suppress "1 change detected" log spam from the watcher library
logging.getLogger('watchfiles').setLevel(logging.WARNING)


class TalosAgentConstants:
    """Protocol Constants."""

    # Meta
    VERSION = '3.1.0'
    ENCODING = 'utf-8'
    ERR_HANDLER = 'replace'

    # Networking
    BUFFER_SIZE = 1024 * 128  # 128KB Process Buffer
    TCP_CHUNK = 65536  # 64KB Network Chunk
    TIMEOUT_LOG_APPEAR = 10.0

    # JSON Protocol Keys
    K_CMD = 'cmd'
    K_ARGS = 'args'
    K_STATUS = 'status'
    K_MSG = 'msg'
    K_DATA = 'data'
    K_TYPE = 'type'
    K_CONTENT = 'content'
    K_CODE = 'code'
    K_HOST = 'hostname'
    K_VER = 'version'

    # Commands
    CMD_PING = 'PING'
    CMD_EXECUTE = 'EXECUTE'
    CMD_UPDATE = 'UPDATE_SELF'

    # Statuses / Types
    S_PONG = 'PONG'
    S_OK = 'OK'
    S_ERROR = 'ERROR'
    S_UPDATING = 'UPDATING'
    T_LOG = 'log'
    T_EXIT = 'exit'

    # Logging Tags
    TAG_MONITOR = '[MONITOR]'
    TAG_AGENT = '[AGENT]'


# ==========================================
# PART 1: The Engine (Runner + Monitor)
# ==========================================


class AsyncProcessRunner:
    """
    Manages a subprocess lifecycle and streams STDOUT/STDERR.
    Holds the process handle to prevent zombies.
    """

    def __init__(self, command: List[str], cwd: Optional[str] = None):
        self.command = command
        self.cwd = cwd
        self.process: Optional[asyncio.subprocess.Process] = None

    async def start(self) -> None:
        """Launches the subprocess using explicit program + args separation."""
        if not self.command:
            raise ValueError('Command list cannot be empty')

        # Explicitly split program from arguments
        program = self.command[0]
        args = self.command[1:]

        self.process = await asyncio.create_subprocess_exec(
            program,
            *args,
            cwd=self.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            limit=TalosAgentConstants.BUFFER_SIZE,
        )

    async def stream_output(self) -> AsyncGenerator[str, None]:
        """Yields decoded lines from the process output."""
        if not self.process or not self.process.stdout:
            return

        async for line in self.process.stdout:
            if line:
                yield line.decode(
                    TalosAgentConstants.ENCODING,
                    errors=TalosAgentConstants.ERR_HANDLER,
                )

    async def wait(self) -> Optional[int]:
        """Waits for process exit and returns exit code."""
        if self.process:
            return await self.process.wait()
        return None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def kill(self) -> None:
        """Forcefully kills the process tree."""
        if self.process:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass


class AsyncLogMonitor:
    """
    Event-driven file watcher.
    Waits for a file to appear, then tails it respecting rotation/truncation.
    """

    def __init__(self, file_path: str, launch_time: float = 0.0):
        self.file_path = file_path
        self.launch_time = launch_time

        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._watcher_task: Optional[asyncio.Task] = None
        self._current_offset = 0
        self._stop_event = asyncio.Event()
        self._file_found = False

    async def start(self) -> None:
        if not self._watcher_task:
            self._watcher_task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

        if not self._file_found:
            self._queue.put_nowait(
                f"\n{TalosAgentConstants.TAG_MONITOR} Info: Log file '{self.file_path}' never appeared.\n"
            )

    async def check_for_lines(self) -> List[str]:
        """Consumer method: Drains all currently queued lines."""
        if not self._watcher_task:
            await self.start()

        # "anti-pattern" for asyncio
        # would make it more instant and may miss a small file.
        # removed 1/24/2025 may consider later.
        # self._read_file()  ### AI ADDED THIS HERE?!?!?

        lines = []
        try:
            while True:
                lines.append(self._queue.get_nowait())
        except asyncio.QueueEmpty:
            pass
        return lines

    async def _watch_loop(self) -> None:
        """Producer loop: Waits for file -> Watches Folder -> Reads Content."""
        directory = os.path.dirname(self.file_path) or '.'

        # 1. Patience Phase: Wait for the FILE itself to exist
        start_time = time.time()
        while time.time() - start_time < TalosAgentConstants.TIMEOUT_LOG_APPEAR:
            if os.path.exists(self.file_path):
                break
            if self._stop_event.is_set():
                return
            await asyncio.sleep(1.0)

        # 2. Watch Phase
        self._read_file()  # Initial read (catch up)

        try:
            # We watch the directory because file updates (writes) trigger dir events
            async for _ in awatch(directory, stop_event=self._stop_event):
                self._read_file()
        except asyncio.CancelledError:
            pass
        except Exception:
            # We trap broad exceptions here only to keep the watcher alive
            # if the file is briefly locked (common on Windows)
            pass

    def _read_file(self) -> None:
        """Reads new data from the file, handling offsets and rotation."""
        if not os.path.exists(self.file_path):
            return

        # Avoid reading stale logs from previous runs
        if os.path.getmtime(self.file_path) < self.launch_time:
            return
        try:
            with open(
                self.file_path,
                'r',
                encoding=TalosAgentConstants.ENCODING,
                errors=TalosAgentConstants.ERR_HANDLER,
            ) as f:
                # Check for Truncation (Log Rotation)
                f.seek(0, os.SEEK_END)
                current_size = f.tell()

                if current_size < self._current_offset:
                    self._current_offset = 0

                f.seek(self._current_offset)

                for line in f:
                    self._queue.put_nowait(line)

                self._current_offset = f.tell()
                self._file_found = True

        except OSError:
            # Specific trap for File Locked / Permission Denied
            pass


async def run_hydra_pipeline(
    command: List[str],
    log_path: Optional[str],
    output_callback: Callable[[str], Awaitable[None]],
) -> int:
    """
    Orchestrates the Process Runner and Log Monitor.
    Feeds all output to the callback.
    """
    runner = AsyncProcessRunner(command)
    monitor = (
        AsyncLogMonitor(log_path, launch_time=time.time()) if log_path else None
    )

    # Task to pipe process STDOUT to the callback
    async def _pipe_process_output():
        async for line in runner.stream_output():
            await output_callback(line)

    # Task to pipe file logs to the callback
    async def _pipe_monitor_output():
        if not monitor:
            return

        while True:
            lines = await monitor.check_for_lines()
            for line in lines:
                await output_callback(line)

            # Check exit conditions
            if not runner.is_running:
                # One final drain after process death
                lines = await monitor.check_for_lines()
                for line in lines:
                    await output_callback(line)
                break

            await asyncio.sleep(0.5)

    # Launch Pipeline
    pipeline_tasks = []

    if monitor:
        await monitor.start()
        pipeline_tasks.append(asyncio.create_task(_pipe_monitor_output()))

    await runner.start()
    process_task = asyncio.create_task(_pipe_process_output())

    exit_code = await runner.wait()
    if exit_code is None:
        exit_code = 1

    # Ensure process stream finishes
    await process_task

    # Clean up monitor
    if monitor:
        await monitor.stop()
        await asyncio.gather(*pipeline_tasks)

    return exit_code


# ==========================================
# PART 2: The Agent Service (TCP)
# ==========================================


class TalosAgent:
    def __init__(self, port: int = 5005):
        self.port = port
        self.running = True
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        # Debug level on for now, as requested
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
        )
        return logging.getLogger('TalosAgent')

    def run(self) -> None:
        """Main entry point. Starts the TCP listener."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('0.0.0.0', self.port))
            server_socket.listen(5)

            self.logger.info(
                f'Talos Agent v{TalosAgentConstants.VERSION} listening on port {self.port}'
            )

            while self.running:
                try:
                    conn, addr = server_socket.accept()
                    # Spin off a thread per connection to allow concurrent jobs
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(conn, addr),
                        daemon=True,
                    )
                    client_thread.start()
                except OSError as e:
                    self.logger.error(f'Socket accept error: {e}')

    def handle_client(self, conn: socket.socket, addr: tuple) -> None:
        """
        Handles a single client connection.
        Reads JSON request -> Routes Command -> Sends JSON response(s).
        """
        try:
            # Tight trap for socket reading
            try:
                data = (
                    conn.recv(TalosAgentConstants.TCP_CHUNK)
                    .decode(TalosAgentConstants.ENCODING)
                    .strip()
                )
            except OSError as e:
                self.logger.warning(f'Socket read failed from {addr}: {e}')
                return

            if not data:
                return

            # Tight trap for JSON parsing
            try:
                request = json.loads(data)
            except json.JSONDecodeError:
                self.logger.error(f'Invalid JSON from {addr}')
                return

            command = request.get(TalosAgentConstants.K_CMD, '').upper()
            args = request.get(TalosAgentConstants.K_ARGS, dict())

            self.logger.debug(f'CMD: {command} from {addr}')

            if command == TalosAgentConstants.CMD_PING:
                self._send_json(
                    conn,
                    dict(
                        status=TalosAgentConstants.S_PONG,
                        hostname=socket.gethostname(),
                        version=TalosAgentConstants.VERSION,
                    ),
                )

            elif command == TalosAgentConstants.CMD_EXECUTE:
                self._handle_execute(conn, args)

            elif command == TalosAgentConstants.CMD_UPDATE:
                self._handle_update(conn, args)

            else:
                self._send_json(
                    conn,
                    dict(
                        status=TalosAgentConstants.S_ERROR,
                        msg=f'Unknown command: {command}',
                    ),
                )

        except Exception as e:
            self.logger.error(f'Handler crash for {addr}: {e}')
            # Try to send error back if socket is still open
            self._send_json(
                conn, dict(status=TalosAgentConstants.S_ERROR, msg=str(e))
            )
        finally:
            conn.close()

    def _handle_execute(self, conn: socket.socket, args: dict) -> None:
        """
        Parses execution args and kicks off the Async Engine.
        """
        executable = args.get('executable')
        params = args.get('params', [])
        log_path = args.get('log_path')

        if not executable:
            self._send_json(
                conn,
                dict(
                    status=TalosAgentConstants.S_ERROR,
                    msg='No executable provided',
                ),
            )
            return

        full_cmd = [executable] + params

        # We must create a new event loop for this thread to run asyncio
        try:
            asyncio.run(self._execute_async_bridge(conn, full_cmd, log_path))
        except Exception as e:
            self.logger.error(f'Execution failed: {e}')

    async def _execute_async_bridge(
        self, conn: socket.socket, command: List[str], log_path: Optional[str]
    ) -> None:
        """
        Async wrapper that bridges the engine callback to the blocking TCP socket.
        """

        # Callback: Send a JSON chunk for every log line
        async def socket_callback(text: str) -> None:
            # Using dict constructor as requested
            payload_data = dict(type=TalosAgentConstants.T_LOG, content=text)
            payload = json.dumps(payload_data)

            # socket.send is blocking, but fast enough for small chunks
            try:
                conn.sendall(
                    (payload + '\n').encode(TalosAgentConstants.ENCODING)
                )
            except OSError:
                # Connection dropped; nothing we can do but abort
                pass

        try:
            # 1. Notify Start
            await socket_callback(
                f'{TalosAgentConstants.TAG_AGENT} Launching: {" ".join(command)}\n'
            )

            # 2. Run Engine
            exit_code = await run_hydra_pipeline(
                command, log_path, socket_callback
            )

            # 3. Notify End
            final_data = dict(type=TalosAgentConstants.T_EXIT, code=exit_code)
            conn.sendall(
                (json.dumps(final_data) + '\n').encode(
                    TalosAgentConstants.ENCODING
                )
            )

        except Exception as e:
            await socket_callback(
                f'{TalosAgentConstants.TAG_AGENT} CRASH: {e}\n'
            )
            error_data = dict(type=TalosAgentConstants.T_EXIT, code=-1)
            conn.sendall(
                (json.dumps(error_data) + '\n').encode(
                    TalosAgentConstants.ENCODING
                )
            )

    def _handle_update(self, conn: socket.socket, args: dict) -> None:
        """
        Overwrites this script and restarts the process.
        """
        content = args.get(TalosAgentConstants.K_CONTENT)
        if not content:
            self._send_json(
                conn,
                dict(
                    status=TalosAgentConstants.S_ERROR,
                    msg='No content provided',
                ),
            )
            return

        self.logger.info('Received self-update request.')

        # 1. Overwrite Self
        target_file = os.path.abspath(__file__)
        try:
            with open(
                target_file, 'w', encoding=TalosAgentConstants.ENCODING
            ) as f:
                f.write(content)
        except OSError as e:
            self._send_json(
                conn,
                dict(
                    status=TalosAgentConstants.S_ERROR, msg=f'Write failed: {e}'
                ),
            )
            return

        self._send_json(conn, dict(status=TalosAgentConstants.S_UPDATING))

        # 2. Restart Logic (Windows Batch File Trick)
        # We create a temp batch file to wait 1s and then relaunch this script
        bat_path = os.path.join(os.path.dirname(target_file), '_restart.bat')
        bat_content = (
            '@echo off\n'
            'timeout /t 1 >nul\n'
            f'"{sys.executable}" "{target_file}"\n'
            'del "%~f0"\n'
        )

        try:
            with open(bat_path, 'w') as f:
                f.write(bat_content)

            subprocess.Popen(
                [bat_path],
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE
                | subprocess.DETACHED_PROCESS,
            )
        except OSError as e:
            self.logger.error(f'Failed to restart: {e}')
            return

        # 3. Die
        self.running = False
        conn.close()
        os._exit(0)

    def _send_json(self, conn: socket.socket, data: dict) -> None:
        """Helper to send a JSON line."""
        try:
            payload = json.dumps(data) + '\n'
            conn.sendall(payload.encode(TalosAgentConstants.ENCODING))
        except OSError:
            pass


if __name__ == '__main__':
    TalosAgent().run()
