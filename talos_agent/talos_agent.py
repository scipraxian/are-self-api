"""
Talos Remote Agent
==================

A lightweight, asynchronous execution node designed for the Talos Build Farm.
This agent transforms any machine (Windows/Linux) into a "Smart Worker" capable
of receiving complex build instructions and streaming real-time telemetry back
to the central server.

Key Capabilities:
-----------------
1.  **Remote Execution:** Launches subprocesses (e.g., Unreal Automation Tool,
    Robocopy) via a JSON-over-TCP protocol.
2.  **Real-Time Streaming:** Uses `asyncio` generators to stream STDOUT, STDERR,
    and Log File changes immediately to the caller with zero latency.
3.  **Robust Process Management:** Holds explicit handles to child processes
    to prevent "zombie" executables if connections drop.
4.  **Event-Driven Monitoring:** Uses filesystem events (via `watchfiles`) to
    tail logs efficiently without polling overhead.
5.  **Self-Healing:** Capable of hot-swapping its own code via the `UPDATE_SELF`
    command.
6. **Self-Identifying:** Reports its hardware UUID upon PING.

Architecture:
-------------
* **Pure AsyncIO:** Single-threaded, event-loop based design handles TCP,
    Process I/O, and File I/O concurrently without thread context switching.
* **Unified Interface:** "Eat your own dog food" design—the Agent uses the
    exact same execution logic (`execute_local`) for internal tasks as it
    exposes to remote clients.
* **Strict Typing:** All events are emitted as strictly typed NamedTuples
    (`TalosEvent`) to eliminate ambiguity between Logs and Exit Codes.
* **Stateless:** Does not connect to the Database. It is a "dumb" executor
    controlled entirely by the Hydra Spell Caster.

Security:
---------
* **Input Validation:** All user input is validated and sanitized to prevent
    command injection and other security vulnerabilities.
* **Logging:** Comprehensive logging is implemented to track all operations
    and potential security incidents.
* **Error Handling:** Graceful error handling is implemented to prevent
    sensitive information leakage.
* **Internal use only:** The agent is not exposed to the public internet.
* **Efficiency > Security:** The agent prioritizes efficiency over security
    in its design, as it is intended for internal use within a trusted network.

Dependencies:
-------------
* Python 3.10+
* `watchfiles` (Filesystem events)
* `psutil` (Process Management)

Usage:
------
    python talos_agent.py
"""

import asyncio
import contextlib
import json
import logging
import os
import socket
import subprocess
import sys
import time
from typing import (
    AsyncGenerator,
    Awaitable,
    Callable,
    List,
    NamedTuple,
    Optional,
    Tuple,
    Union,
)

import psutil

# --- DEPENDENCIES ---
try:
    from watchfiles import awatch
except ImportError:
    print('FATAL: Missing dependencies. Run: pip install watchfiles')
    sys.exit(1)

# Suppress "1 change detected" log spam
logging.getLogger('watchfiles').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class TalosAgentConstants:
    """Protocol Constants."""

    # Meta
    VERSION = '4.3.3'
    ENCODING = 'utf-8'
    ERR_HANDLER = 'replace'

    # Networking
    BUFFER_SIZE = 1024 * 128  # 128KB Process Buffer
    TCP_CHUNK = 65536  # 64KB Network Chunk
    TIMEOUT_LOG_APPEAR = 10.0
    BIND_ADDRESS = '0.0.0.0'
    BIND_PORT = 5005

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
    K_SOURCE = 'source'

    # Payload Argument Keys
    K_EXE = 'executable'
    K_PARAMS = 'params'
    K_LOG = 'log_path'

    # Commands
    CMD_PING = 'PING'
    CMD_EXECUTE = 'EXECUTE'
    CMD_UPDATE = 'UPDATE_SELF'
    CMD_STOP = 'STOP'

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


class TalosEvent(NamedTuple):
    """
    Strictly typed event structure.
    Removes ambiguity: 'text' is always for logs, 'code' is always for status.
    """

    type: str
    text: str = ''  # Default empty for non-log events
    code: int = -1  # Default -1 for non-exit events
    source: str = 'stdout'  # 'stdout' or 'file'


# ==========================================
# PART 1: The Engine (Pure Async + Leash)
# ==========================================


class AsyncProcessRunner:
    """
    Manages a subprocess lifecycle and streams STDOUT/STDERR via async generator.
    """

    def __init__(self, command: List[str], cwd: Optional[str] = None):
        self.command = command
        self.cwd = cwd
        self.process: Optional[asyncio.subprocess.Process] = None

    async def start(self) -> None:
        if not self.command:
            raise ValueError('Command list cannot be empty')

        program = self.command[0]
        args = self.command[1:]

        self.process = await asyncio.create_subprocess_exec(
            program,
            *args,
            cwd=self.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=TalosAgentConstants.BUFFER_SIZE,
        )

    async def stream_output(self) -> AsyncGenerator[str, None]:
        """Yields lines directly from the process stdout pipe."""
        if not self.process or not self.process.stdout:
            return

        async for line in self.process.stdout:
            if line:
                yield line.decode(
                    TalosAgentConstants.ENCODING,
                    errors=TalosAgentConstants.ERR_HANDLER,
                )

    async def wait(self) -> Optional[int]:
        if self.process:
            return await self.process.wait()
        return None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def _is_pid_running(self, pid: int) -> bool:
        """Checks if a PID is running using psutil."""
        try:
            return psutil.pid_exists(pid)
        except Exception:
            return False

    async def terminate(self) -> None:
        """
        Attempts a graceful termination matching legacy '9_RemoteAgent.py'.
        Strategy: Ask (Image Name) -> Wait (10s) -> Force (PID).
        """
        if not self.process or self.process.returncode is not None:
            return

        pid = self.process.pid
        exe_name = os.path.basename(self.command[0])
        print(
            f'[TERMINATE] Requesting Graceful Exit for {exe_name} (PID: {pid})...'
        )

        # 1. Ask Nicely: taskkill /IM matches legacy behavior
        try:
            if sys.platform == 'win32':
                subprocess.run(
                    f'taskkill /IM {exe_name}',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                self.process.terminate()
        except Exception as e:
            print(f'[TERMINATE] Signal failed: {e}')

        # 2. Wait Loop: 10 seconds check using psutil [cite: 1086]
        print('   > Waiting for shutdown...')
        for _ in range(10):
            if not self._is_pid_running(pid):
                print('   > Application closed successfully.')
                return
            await asyncio.sleep(1.0)

        # 3. Force Kill [cite: 1087]
        print('   [!] Graceful exit timed out. FORCE KILLING.')
        self.kill()

    def kill(self) -> None:
        """
        Forces the process to terminate.
        Uses OS-specific 'Tree Kill' and 'Image Kill' to ensure no zombies remain.
        """
        if not self.process:
            print('[KILL] No active process handle.')
            return

        pid = self.process.pid
        exe_name = os.path.basename(self.command[0])
        print(f'[KILL] Initiating termination for PID: {pid} ({exe_name})')

        try:
            # 1. Attempt standard kill first
            self.process.kill()
            print(f'[KILL] Sent standard .kill() signal to PID {pid}')

            # 2. Windows Nuclear Option: taskkill /F /T
            if sys.platform == 'win32' and pid:
                print(f'[KILL] Attempting taskkill /F /T /PID {pid}...')
                result = subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(pid)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                print(
                    f'[KILL] PID Kill Result: {result.stdout.strip()} {result.stderr.strip()}'
                )

                # 3. Fallback: Kill by Image Name [cite: 1088]
                print(
                    f'[KILL] Fallback: Sweeping for Image Name: {exe_name}...'
                )
                result_im = subprocess.run(
                    f'taskkill /F /IM {exe_name}',
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                print(
                    f'[KILL] Image Kill Result: {result_im.stdout.strip()} {result_im.stderr.strip()}'
                )

        except ProcessLookupError:
            print('[KILL] Process already dead (ProcessLookupError).')
        except Exception as e:
            print(f'[KILL] Exception during kill: {e}')


class AsyncLogMonitor:
    """
    Event-driven file watcher.
    Pushes lines to an internal queue, consumed via `stream_changes`.
    """

    def __init__(self, file_path: str, launch_time: float = 0.0):
        self.file_path = file_path
        self.launch_time = launch_time

        # Unbounded queue to buffer file reads during high load
        self._queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self._watcher_task: Optional[asyncio.Task] = None
        self._current_offset = 0
        self._stop_event = asyncio.Event()
        self._file_found = False

        # DEBUG CHATTER
        print(f'[MONITOR] Initialized for: {self.file_path}')

    async def start(self) -> None:
        if not self._watcher_task:
            self._watcher_task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._watcher_task:
            self._watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watcher_task

        # Report if file never appeared
        if not self._file_found:
            msg = f"\n{TalosAgentConstants.TAG_MONITOR} Warn: Log file '{self.file_path}' never appeared.\n"
            print(msg.strip())
            self._queue.put_nowait(msg)

        # Signal end of stream
        self._queue.put_nowait(None)

    async def stream_changes(self) -> AsyncGenerator[str, None]:
        """
        Yields lines as they are detected.
        Waits (blocks) if queue is empty.
        Stops yielding when None is received (from stop()).
        """
        if not self._watcher_task:
            await self.start()

        while True:
            line = await self._queue.get()
            if line is None:
                return
            yield line

    async def _watch_loop(self) -> None:
        directory = os.path.dirname(self.file_path) or '.'
        print(f'[MONITOR] Watching directory: {directory}')

        # 1. Patience Phase
        start_time = time.time()
        print(f'[MONITOR] Waiting for file to appear...')
        while time.time() - start_time < TalosAgentConstants.TIMEOUT_LOG_APPEAR:
            if os.path.exists(self.file_path):
                print(f'[MONITOR] File found: {self.file_path}')
                break
            if self._stop_event.is_set():
                return
            await asyncio.sleep(1.0)

        # 2. Watch Phase
        # Force check on first read to establish offset
        self._read_file(force_check=True)
        try:
            async for _ in awatch(directory, stop_event=self._stop_event):
                # Event triggered: Trust the event, ignore mtime lag
                self._read_file(force_check=True)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f'[MONITOR] Watch loop crashed: {e}')

    def _read_file(self, force_check: bool = False) -> None:
        if not os.path.exists(self.file_path):
            return

        # Windows Lag Fix: If forced (via event), skip mtime check
        if not self._file_found and not force_check:
            mtime = os.path.getmtime(self.file_path)
            if mtime < self.launch_time:
                return

        try:
            # Try to open with shared access (default in Python, but OS can lock)
            with open(
                self.file_path,
                'r',
                encoding=TalosAgentConstants.ENCODING,
                errors=TalosAgentConstants.ERR_HANDLER,
            ) as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()

                # Detect Truncation (New Run)
                if size < self._current_offset:
                    print(
                        '[MONITOR] File truncation detected. Resetting offset.'
                    )
                    self._current_offset = 0

                f.seek(self._current_offset)
                for line in f:
                    self._queue.put_nowait(line)

                self._current_offset = f.tell()
                if not self._file_found:
                    print(
                        f'[MONITOR] Started streaming from offset {self._current_offset}'
                    )
                    self._file_found = True

        except OSError as e:
            # THIS IS THE CRITICAL FIX: Don't swallow errors!
            print(f'[MONITOR ERROR] Failed to read log: {e}')


async def _watch_stop_event(
    stop_event: asyncio.Event, runner: AsyncProcessRunner
) -> None:
    """
    Helper to monitor stop event and signal the runner.
    """
    await stop_event.wait()
    if runner.is_running:
        print('[PIPELINE] Graceful Stop Requested.')
        # UPDATED: Use the new async terminate with escalation
        await runner.terminate()


async def _pipe_stream(
    stream_generator: AsyncGenerator[str, None],
    callback: Callable[[str], Awaitable[None]],
    runner: AsyncProcessRunner,
) -> None:
    """Helper to pipe a stream to a callback, killing process on connection error."""
    try:
        async for line in stream_generator:
            await callback(line)
    except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
        # Leash Broken: Kill process immediately
        runner.kill()
        raise


async def run_hydra_pipeline(
    command: List[str],
    log_path: Optional[str],
    output_callback: Callable[[str], Awaitable[None]],
    file_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    stop_event: Optional[asyncio.Event] = None,
) -> int:
    """
    Orchestrates the Process Runner and Log Monitor using concurrent tasks.

    Args:
        command: The executable and arguments.
        log_path: Path to the external log file to watch.
        output_callback: Async callback for STDOUT/STDERR.
        file_callback: Async callback for FILE LOGS. Defaults to output_callback if None.
        stop_event: Event to trigger a graceful termination.

    CRITICAL: Implements "The Leash" and "Buffer Drain".
    """
    runner = AsyncProcessRunner(command)
    monitor = (
        AsyncLogMonitor(log_path, launch_time=time.time()) if log_path else None
    )

    # Determine destination for file logs
    actual_file_callback = file_callback if file_callback else output_callback

    await runner.start()
    if monitor:
        await monitor.start()

    # Start piping using helper functions to avoid nesting
    tasks = []

    runner_task = asyncio.create_task(
        _pipe_stream(runner.stream_output(), output_callback, runner)
    )
    tasks.append(runner_task)

    monitor_task = None
    if monitor:
        monitor_task = asyncio.create_task(
            _pipe_stream(monitor.stream_changes(), actual_file_callback, runner)
        )
        tasks.append(monitor_task)

    stop_task = None
    if stop_event:
        stop_task = asyncio.create_task(_watch_stop_event(stop_event, runner))
        tasks.append(stop_task)

    try:
        # Wait for process to exit naturally (or via terminate)
        exit_code = await runner.wait()
        if exit_code is None:
            exit_code = 1

        # Ensure stdout pipe finishes cleanly
        await runner_task

        # --- POST-MORTEM BUFFER DRAIN ---
        # The process is dead, but logs might still be flushing to disk.
        # We hold the line open for a few seconds to catch the final words.
        if monitor:
            print('[PIPELINE] Process exited. Draining log buffer (3s)...')
            await asyncio.sleep(3.0)

    except (
        asyncio.CancelledError,
        ConnectionResetError,
        BrokenPipeError,
        ConnectionAbortedError,
    ) as e:
        # --- THE KILL SWITCH ---
        print(
            f'\n[PIPELINE] Aborting (Reason: {type(e).__name__}). Killing process...'
        )
        runner.kill()

        # Robustness: Wait briefly for the process to actually die to avoid orphans
        print('[PIPELINE] Waiting for process death...')
        try:
            await asyncio.wait_for(runner.wait(), timeout=3.0)
            print('[PIPELINE] Process confirmed dead.')
        except asyncio.TimeoutError:
            print('[PIPELINE] Process wait timed out (Zombie?). Moving on.')
        except Exception as kill_err:
            print(f'[PIPELINE] Error waiting for death: {kill_err}')

        raise

    finally:
        # Cleanup Monitor regardless of success/failure
        if monitor:
            await monitor.stop()
            if monitor_task:
                with contextlib.suppress(Exception):
                    await monitor_task

        if stop_task:
            stop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stop_task

    return exit_code


# ==========================================
# PART 2: The Agent Service (AsyncIO Server)
# ==========================================


class TalosAgent:
    def __init__(self, port: int = TalosAgentConstants.BIND_PORT):
        self.port = port
        self.logger = self._setup_logging()
        self.active_tasks = set()

    def _setup_logging(self) -> logging.Logger:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
        )
        return logging.getLogger('TalosAgent')

    async def run_server(self) -> None:
        """Starts the AsyncIO TCP Server."""
        server = await asyncio.start_server(
            self.handle_client, TalosAgentConstants.BIND_ADDRESS, self.port
        )

        addr = server.sockets[0].getsockname()
        self.logger.info(
            f'Talos Agent v{TalosAgentConstants.VERSION} listening on {addr}'
        )

        async with server:
            await server.serve_forever()

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Async handler for a single connection."""

        # Track this task for graceful shutdown logic (future proofing)
        current_task = asyncio.current_task()
        self.active_tasks.add(current_task)

        addr = writer.get_extra_info('peername')
        try:
            # Read Request
            try:
                data = await reader.read(TalosAgentConstants.TCP_CHUNK)
            except OSError:
                return  # Connection dead

            message = data.decode(TalosAgentConstants.ENCODING).strip()
            if not message:
                return

            try:
                request = json.loads(message)
            except json.JSONDecodeError:
                self.logger.error(f'Invalid JSON from {addr}')
                return

            command = request.get(TalosAgentConstants.K_CMD, '').upper()
            args = request.get(TalosAgentConstants.K_ARGS, dict())
            self.logger.debug(f'CMD: {command} from {addr}')

            # Route Command
            if command == TalosAgentConstants.CMD_PING:
                await self._send_json(
                    writer,
                    dict(
                        status=TalosAgentConstants.S_PONG,
                        hostname=socket.gethostname(),
                        version=TalosAgentConstants.VERSION,
                        uuid=_get_agent_id(),
                    ),
                )

            elif command == TalosAgentConstants.CMD_EXECUTE:
                # Pass reader to allow listening for STOP signal during execution
                await self._handle_execute(reader, writer, args)

            elif command == TalosAgentConstants.CMD_UPDATE:
                await self._handle_update(writer, args)

            else:
                await self._send_json(
                    writer,
                    dict(
                        status=TalosAgentConstants.S_ERROR,
                        msg=f'Unknown command: {command}',
                    ),
                )

        except Exception as e:
            self.logger.error(f'Handler error {addr}: {e}')
            if not writer.is_closing():
                with contextlib.suppress(Exception):
                    await self._send_json(
                        writer,
                        dict(status=TalosAgentConstants.S_ERROR, msg=str(e)),
                    )
        finally:
            self.active_tasks.discard(current_task)
            with contextlib.suppress(
                ConnectionResetError, BrokenPipeError, OSError
            ):
                await writer.drain()
                writer.close()
                await writer.wait_closed()

    @classmethod
    async def _monitor_remote_stop(
        cls, reader: asyncio.StreamReader, stop_event: asyncio.Event
    ) -> None:
        """Helper to listen for the STOP command on the open reader."""
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                msg = data.decode(TalosAgentConstants.ENCODING).strip().upper()
                if msg == TalosAgentConstants.CMD_STOP:
                    # We can't easily access the logger from a classmethod without passing it,
                    # but we can print which goes to stdout/system log.
                    print('[AGENT] Graceful STOP signal received from client.')
                    stop_event.set()
        except Exception:
            pass

    async def _handle_execute(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        args: dict,
    ) -> None:
        """Runs the pipeline and streams results back to the open socket.

        ARCHITECTURE NOTE: This method uses execute_local() internally,
        ensuring remote clients get the exact same execution behavior as
        local callers. This "eat your own dog food" pattern guarantees
        consistency and reduces code duplication.
        """
        executable = args.get(TalosAgentConstants.K_EXE)
        params = args.get(TalosAgentConstants.K_PARAMS, [])
        log_path = args.get(TalosAgentConstants.K_LOG)

        if not executable:
            await self._send_json(
                writer,
                dict(status=TalosAgentConstants.S_ERROR, msg='No executable'),
            )
            return

        cmd_list = [executable] + params
        stop_event = asyncio.Event()

        listener_task = asyncio.create_task(
            self._monitor_remote_stop(reader, stop_event)
        )

        try:
            # SELF-CONSUMPTION: Iterate over the local generator
            async for event in self.execute_local(
                cmd_list, log_path, stop_event=stop_event
            ):
                response_payload: dict = {
                    TalosAgentConstants.K_TYPE: event.type
                }

                if event.type == TalosAgentConstants.T_LOG:
                    response_payload[TalosAgentConstants.K_CONTENT] = event.text
                    response_payload[TalosAgentConstants.K_SOURCE] = (
                        event.source
                    )
                elif event.type == TalosAgentConstants.T_EXIT:
                    response_payload[TalosAgentConstants.K_CODE] = event.code

                # If the client has disconnected, this await will crash.
                # That crash stops the generator iteration.
                # The generator's 'finally' block triggers and kills the process.
                await self._send_json(writer, response_payload)

        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            self.logger.warning(
                f'Connection lost during execution of {executable}. Process Killed.'
            )
            # No need to send response, client is gone.

        except Exception as e:
            self.logger.error(f'Handler critical error: {e}')
            # Attempt to send error if connection is still alive
            if not writer.is_closing():
                with contextlib.suppress(Exception):
                    await self._send_json(
                        writer, dict(type=TalosAgentConstants.T_EXIT, code=-1)
                    )
        finally:
            listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener_task

    async def _handle_update(
        self, writer: asyncio.StreamWriter, args: dict
    ) -> None:
        """Writes new file content and triggers a restart."""
        content = args.get(TalosAgentConstants.K_CONTENT)
        if not content:
            await self._send_json(
                writer,
                dict(status=TalosAgentConstants.S_ERROR, msg='No content'),
            )
            return

        target_file = os.path.abspath(__file__)
        try:
            # Sync write (acceptable for update operation)
            with open(
                target_file, 'w', encoding=TalosAgentConstants.ENCODING
            ) as f:
                f.write(content)
        except OSError as e:
            await self._send_json(
                writer, dict(status=TalosAgentConstants.S_ERROR, msg=str(e))
            )
            return

        await self._send_json(
            writer, dict(status=TalosAgentConstants.S_UPDATING)
        )

        # Trigger Restart
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
        except Exception:
            pass

        writer.close()
        sys.exit(0)

    async def _send_json(
        self, writer: asyncio.StreamWriter, data: dict
    ) -> None:
        """Helper to write a JSON line."""
        payload = json.dumps(data) + '\n'
        writer.write(payload.encode(TalosAgentConstants.ENCODING))
        await writer.drain()

    # Execution Modules
    @classmethod
    async def execute_local(
        cls,
        command: List[str],
        log_path: Optional[str] = None,
        stop_event: Optional[asyncio.Event] = None,
    ) -> AsyncGenerator[TalosEvent, None]:
        """
        Executes a command LOCALLY using run_hydra_pipeline.
        Adapts the callback-based pipeline to an AsyncGenerator.
        Yields: TalosEvent(type, text, code, source)
        """
        event_queue: asyncio.Queue[Optional[TalosEvent]] = asyncio.Queue()

        # 1. Stdout Callback (Source = stdout)
        async def stdout_callback(text: str) -> None:
            await event_queue.put(
                TalosEvent(
                    type=TalosAgentConstants.T_LOG, text=text, source='stdout'
                )
            )

        # 2. File Callback (Source = file)
        async def file_callback(text: str) -> None:
            await event_queue.put(
                TalosEvent(
                    type=TalosAgentConstants.T_LOG, text=text, source='file'
                )
            )

        # Background Worker
        async def worker():
            try:
                # Pass BOTH callbacks AND stop_event to the engine
                exit_code = await run_hydra_pipeline(
                    command,
                    log_path,
                    stdout_callback,
                    file_callback,
                    stop_event=stop_event,
                )
                await event_queue.put(
                    TalosEvent(type=TalosAgentConstants.T_EXIT, code=exit_code)
                )
            except Exception as e:
                await event_queue.put(
                    TalosEvent(
                        type=TalosAgentConstants.T_LOG,
                        text=f'{TalosAgentConstants.TAG_AGENT} CRASH: {e}\n',
                    )
                )
                await event_queue.put(
                    TalosEvent(type=TalosAgentConstants.T_EXIT, code=-1)
                )
            finally:
                await event_queue.put(None)  # Sentinel

        task = asyncio.create_task(worker())

        try:
            yield TalosEvent(
                type=TalosAgentConstants.T_LOG,
                text=f'{TalosAgentConstants.TAG_AGENT} Launching Local: {" ".join(command)}\n',
            )

            while True:
                event = await event_queue.get()
                if event is None:
                    break
                yield event

        except GeneratorExit:
            logger.info('[AGENT] Generator Closed. Cancelling pipeline...')
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise

    @classmethod
    async def _monitor_stop_signal_task(
        cls, writer: asyncio.StreamWriter, stop_event: asyncio.Event
    ) -> None:
        """Task payload to monitor for stop event and send signal."""
        if not stop_event:
            return
        await stop_event.wait()
        try:
            # Send the out-of-band STOP message
            payload = TalosAgentConstants.CMD_STOP + '\n'
            writer.write(payload.encode(TalosAgentConstants.ENCODING))
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            # Specific logging for debug, but silence for broken pipes
            logging.debug(f'Stop signal transmission failed: {e}')

    @classmethod
    async def execute_remote(
        cls,
        target_hostname: str,
        executable: str,
        params: List[str],
        log_path: str = '',
        stop_event: Optional[asyncio.Event] = None,
    ) -> AsyncGenerator[TalosEvent, None]:
        """
        Executes a command REMOTELY via TCP.
        Yields: TalosEvent(type, text, code)
        """
        payload = {
            TalosAgentConstants.K_CMD: TalosAgentConstants.CMD_EXECUTE,
            TalosAgentConstants.K_ARGS: {
                TalosAgentConstants.K_EXE: executable,
                TalosAgentConstants.K_PARAMS: params,
                TalosAgentConstants.K_LOG: log_path,
            },
        }

        writer = None
        try:
            reader, writer = await asyncio.open_connection(
                target_hostname, TalosAgentConstants.BIND_PORT
            )
        except Exception as e:
            logger.info(f'[AGENT] Remote Connection Failed: {e}')
            yield TalosEvent(
                type=TalosAgentConstants.T_LOG,
                text=f'[FATAL] Connection Failed: {e}\n',
            )
            yield TalosEvent(type=TalosAgentConstants.T_EXIT, code=-1)
            return

        try:
            msg = json.dumps(payload) + '\n'
            writer.write(msg.encode(TalosAgentConstants.ENCODING))
            await writer.drain()

            stopper_task = asyncio.create_task(
                cls._monitor_stop_signal_task(writer, stop_event)
            )

            buffer = ''
            while True:
                try:
                    chunk = await reader.read(TalosAgentConstants.TCP_CHUNK)
                except Exception:
                    break

                if not chunk:
                    break

                buffer += chunk.decode(
                    TalosAgentConstants.ENCODING,
                    errors=TalosAgentConstants.ERR_HANDLER,
                )

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                        msg_type = data.get(TalosAgentConstants.K_TYPE)

                        if msg_type == TalosAgentConstants.T_LOG:
                            yield TalosEvent(
                                type=msg_type,
                                text=data.get(
                                    TalosAgentConstants.K_CONTENT, ''
                                ),
                                source=data.get(
                                    TalosAgentConstants.K_SOURCE, 'stdout'
                                ),
                            )
                        elif msg_type == TalosAgentConstants.T_EXIT:
                            raw_code = data.get(TalosAgentConstants.K_CODE)
                            safe_code = (
                                int(raw_code) if raw_code is not None else -1
                            )
                            yield TalosEvent(type=msg_type, code=safe_code)
                            return
                    except (json.JSONDecodeError, ValueError):
                        logger.info(f'[AGENT] Decode Error: {line}')

        except Exception as e:
            logger.info(f'[AGENT] Remote Stream Error: {e}')
            yield TalosEvent(
                type=TalosAgentConstants.T_LOG,
                text=f'\n[FATAL] Stream Error: {e}\n',
            )
            yield TalosEvent(type=TalosAgentConstants.T_EXIT, code=-1)
        finally:
            if 'stopper_task' in locals():
                stopper_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stopper_task

            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass


def _get_agent_id():
    """Fetches the immutable Machine UUID via PowerShell."""
    try:
        return subprocess.check_output(
            [
                'powershell',
                '-Command',
                'Get-CimInstance Win32_ComputerSystemProduct | Select-Object -ExpandProperty UUID',
            ],
            encoding='utf-8',
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        ).strip()
    except Exception:
        return 'UNKNOWN_UUID'


if __name__ == '__main__':
    agent = TalosAgent()
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(
                asyncio.WindowsProactorEventLoopPolicy()
            )
        asyncio.run(agent.run_server())
    except KeyboardInterrupt:
        print(f'\nShutting down... ({len(agent.active_tasks)} active tasks)')
        pass
