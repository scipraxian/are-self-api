import asyncio
import logging
import re
import sys
import time
import traceback
import uuid
from typing import List, Optional

from asgiref.sync import sync_to_async

from environments.variable_renderer import VariableRenderer
from hydra.models import HydraHead, HydraHeadStatus
from hydra.spells.spell_casters.begin_play_node import begin_play
from hydra.spells.spell_casters.spell_handlers.version_metadata_handler import (
    update_version_metadata,
)
from hydra.spells.spell_casters.spellbook_logic_node import spellbook_logic_node
from hydra.utils import (
    get_active_environment,
    resolve_environment_context,
)
from talos_agent.talos_agent import (
    TalosAgent,
    TalosAgentConstants,
)
from talos_agent.talos_agent_finder import scan_and_register
from talos_reasoning.frontal_lobe import (
    run_frontal_lobe,
)

logger = logging.getLogger(__name__)

BLACKBOARD_SET_KEY = '::blackboard_set '
BLACKBOARD_SET_KEY_REGEX = re.compile(
    r'^.*?::blackboard_set\s+(.+?)::(.*)$', flags=re.MULTILINE
)
BLACKBOARD_SET_STRIPPER = re.compile(
    r'^.*?::blackboard_set\s+.*?::.*$\n?', flags=re.MULTILINE
)


# Native Python Handlers
# TODO: these should only be internal nodes like begin_play,logic_node,sequence.
# NOTE: DO NOT USE THIS METHOD UNLESS YOU KNOW EXACTLY WHAT YOU ARE DOING
# Instead use a management command with a spell. This is for special cases.
NATIVE_HANDLERS = dict(
    begin_play=begin_play,
    update_version_metadata=update_version_metadata,  # TODO: move to management
    scan_and_register=scan_and_register,  # TODO: move to management
    spellbook_logic_node=spellbook_logic_node,
    run_frontal_lobe=run_frontal_lobe,
)


def evaluate_return_code(executable_name: str, return_code: int) -> bool:
    """
    Standardizes success evaluation based on the binary context.
    """
    if 'robocopy' in executable_name.lower():
        # Robocopy codes 0-7 are technically variations of success
        return 0 <= return_code < 8

    # Standard binary success
    return return_code == 0


class AsyncLogManager:
    """
    Handles buffered log writes to the Database with async safety.
    Separates System Output (Execution Log) from Game Output (Spell Log).
    """

    def __init__(self, head: HydraHead, flush_size=50, flush_interval=1.0):
        self.head = head
        self.exec_buffer: List[str] = []
        self.spell_buffer: List[str] = []
        self._lock = asyncio.Lock()
        self._last_flush_time = time.time()
        self._flush_size = flush_size
        self._flush_interval = flush_interval

    async def append(self, text: str):
        async with self._lock:
            self.exec_buffer.append(text)
            if self._should_flush():
                await self._flush_unsafe()

    async def append_spell(self, text: str):
        """Appends to Spell Log (Game Logs/File)."""
        async with self._lock:
            self.spell_buffer.append(text)
            if self._should_flush():
                await self._flush_unsafe()

    async def write_immediate(self, text: str):
        """Writes to Execution Log immediately and logs to system."""
        # Double Log: Ensures we see it in the Server Console (Celery) AND the DB
        logger.info(f'[HEAD {self.head.id}] {text.strip()}')
        async with self._lock:
            await self._flush_unsafe()
            self.head.execution_log += text
            await self._save_to_db()

    async def flush(self):
        async with self._lock:
            await self._flush_unsafe()

    def _should_flush(self) -> bool:
        total_size = len(self.exec_buffer) + len(self.spell_buffer)
        return (
            total_size > self._flush_size
            or (time.time() - self._last_flush_time) > self._flush_interval
        )

    async def _flush_unsafe(self):
        if not self.exec_buffer and not self.spell_buffer:
            return

        if self.exec_buffer:
            self.head.execution_log += ''.join(self.exec_buffer)
            self.exec_buffer.clear()

        if self.spell_buffer:
            self.head.application_log += ''.join(self.spell_buffer)
            self.spell_buffer.clear()

        await self._save_to_db()
        self._last_flush_time = time.time()

    async def _save_to_db(self):
        """
        Saves logs AND checks for ABORT signals from the Manager.
        """
        try:
            await sync_to_async(self.head.refresh_from_db)(fields=['status'])
            if self.head.status_id == HydraHeadStatus.ABORTED:
                raise ConnectionAbortedError('Hydra Head Aborted by User')
            await sync_to_async(self.head.save)(
                update_fields=['execution_log', 'application_log']
            )
        except ConnectionAbortedError:
            raise
        except Exception as e:
            logger.error(
                f'Failed to save execution log for Head {self.head.id}: {e}'
            )


class GenericSpellCaster:
    """The Orchestrator for Talos Spells."""

    LOG_START_MESSAGE = 'Starting spell execution.\n'
    STATUS_STREAMING_LOGS = 100

    STATUSES_WHICH_HALT = [
        HydraHeadStatus.FAILED,
        HydraHeadStatus.ABORTED,
        HydraHeadStatus.STOPPING,
        HydraHeadStatus.STOPPED,
    ]

    EXECUTION_LOG_FIELD = 'execution_log'
    APPLICATION_LOG_FIELD = 'application_log'
    STATUS_FIELD = 'status'
    BLACKBOARD_FIELD = 'blackboard'

    def __init__(self, head_id: uuid.UUID):
        self.head_id = head_id
        self.verbose_logging = True
        self.head: Optional[HydraHead] = None
        self.spell = None
        self.status = HydraHeadStatus.CREATED
        self.logger: Optional[AsyncLogManager] = None
        self.stop_event = asyncio.Event()

    def execute(self):
        """Public Synchronous Entry Point."""
        logger.info(f'Initializing execution for Head ID: {self.head_id}')
        try:
            self._load_head_sync()
        except Exception as e:
            logger.error(f'FATAL: Could not load HydraHead {self.head_id}: {e}')
            return

        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(
                asyncio.WindowsProactorEventLoopPolicy()
            )

        try:
            asyncio.run(self._execute_async())
        except Exception as e:
            self._handle_fatal_error_sync(e)

    async def _execute_async(self):
        """The Main Async Event Loop."""
        try:
            self.logger = AsyncLogManager(self.head)
            await self._preflight()

            spell_task = asyncio.create_task(self._cast_spell())
            monitor_task = asyncio.create_task(self._monitor_abort_signal())

            done, pending = await asyncio.wait(
                [spell_task, monitor_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if monitor_task in done:
                try:
                    exc = monitor_task.exception()
                    if exc:
                        raise exc
                except ConnectionAbortedError:
                    logger.warning(
                        f'Head {self.head_id} execution aborted by user.'
                    )
                    return

            if spell_task in done:
                exc = spell_task.exception()
                if exc:
                    raise exc

        except ConnectionAbortedError:
            pass
        except Exception as e:
            await self._handle_fatal_error(e)

    async def _monitor_abort_signal(self):
        """
        Background task that checks DB status.
        Uses LINEAR BACKOFF to reduce DB pressure on long jobs.
        """
        check_interval = 1.0
        max_interval = 5.0

        while True:
            await asyncio.sleep(check_interval)
            await sync_to_async(self.head.refresh_from_db)(fields=['status'])

            if self.head.status_id == HydraHeadStatus.ABORTED:
                if self.logger:
                    await self.logger.write_immediate(
                        '\n[ABORT] Received Kill Signal.\n'
                    )
                raise ConnectionAbortedError('Aborted by User')

            # Graceful Stop Signal Check
            if self.head.status_id == HydraHeadStatus.STOPPING:
                if not self.stop_event.is_set():
                    # Signal the pipeline loop
                    self.stop_event.set()

            if check_interval < max_interval:
                check_interval = min(check_interval + 0.5, max_interval)

    async def _cast_spell(self):
        self._log_info(f'Launching {self.spell.name}')
        await self._update_status(HydraHeadStatus.RUNNING)

        await self._executable_router()

        if self.status not in self.STATUSES_WHICH_HALT:
            self.status = HydraHeadStatus.SUCCESS
            await self._update_status(HydraHeadStatus.SUCCESS)

    async def _executable_router(self):
        """
        Routes execution to internal python handlers or the unified pipeline.
        """
        if self.spell.talos_executable.internal:
            await self._execute_local_python()
        else:
            await self._execute_unified_pipeline()

    async def _execute_unified_pipeline(self):
        """
        Uses TalosAgent to run the spell either locally or remotely.
        Replaces the old _execute_local_popen.
        """
        # 1. Prepare Arguments
        env = await sync_to_async(get_active_environment)(self.head)
        full_context = await sync_to_async(resolve_environment_context)(
            head_id=self.head_id
        )

        full_cmd = await sync_to_async(self.spell.get_full_command)(
            environment=env, extra_context=full_context
        )

        executable = full_cmd[0]
        params = full_cmd[1:]

        raw_log_path = self.spell.talos_executable.log
        log_path = VariableRenderer.render_string(raw_log_path, full_context)

        is_remote = self.head.target is not None
        target_name = self.head.target.hostname if is_remote else 'Local Server'

        await self.logger.write_immediate(
            f'[ROUTER] Target: {target_name}\n[CMD] {" ".join(full_cmd)}\n'
        )
        self.status = self.STATUS_STREAMING_LOGS

        if is_remote:
            event_stream = TalosAgent.execute_remote(
                target_hostname=self.head.target.hostname,
                executable=executable,
                params=params,
                log_path=log_path,
                stop_event=self.stop_event,
            )
        else:
            event_stream = TalosAgent.execute_local(
                command=full_cmd,
                log_path=log_path,
                stop_event=self.stop_event,
            )

        exit_code = -1
        try:
            async for event in event_stream:
                if event.type == TalosAgentConstants.T_LOG:
                    text_to_log = event.text
                    if BLACKBOARD_SET_KEY in text_to_log:
                        self._log_info('Blackboard update detected.')
                        matches = list(
                            BLACKBOARD_SET_KEY_REGEX.finditer(text_to_log)
                        )
                        for match in matches:
                            key = match.group(1).strip()
                            val = match.group(2).strip()
                            if not isinstance(self.head.blackboard, dict):
                                self.head.blackboard = {}
                            self.head.blackboard[key] = val
                            self._log_info(
                                f'Blackboard updated with {key}={val}.'
                            )
                        text_to_log = BLACKBOARD_SET_STRIPPER.sub(
                            '', text_to_log
                        )
                    if text_to_log:
                        await self.logger.append_spell(text_to_log)
                elif event.type == TalosAgentConstants.T_EXIT:
                    exit_code = event.code
        except Exception as e:
            await self.logger.write_immediate(f'\n[STREAM ERROR] {e}\n')
            self.status = HydraHeadStatus.FAILED
            await self._update_status(HydraHeadStatus.FAILED)
            return

        # Check for Graceful Stop Outcome
        await sync_to_async(self.head.refresh_from_db)(fields=['status'])

        if self.head.status_id == HydraHeadStatus.STOPPING:
            await self.logger.write_immediate(
                '\n[STOP] Process finished. Draining log buffer (3s)...\n'
            )
            # The "Post-Mortem" Delay to catch file flush
            await asyncio.sleep(3.0)
            await self.logger.flush()

            new_status = HydraHeadStatus.STOPPED
            await self.logger.write_immediate(
                '[STOP] Buffer Drained. Stopped.\n'
            )
        else:
            # Normal completion
            await self.logger.flush()
            is_success = evaluate_return_code(executable, exit_code)

            if is_success:
                await self.logger.write_immediate(
                    f'\n[EXIT] Success (Code {exit_code}).\n'
                )
                new_status = HydraHeadStatus.SUCCESS
            else:
                await self.logger.write_immediate(
                    f'\n[EXIT] Process failed with code {exit_code}\n'
                )
                new_status = HydraHeadStatus.FAILED

        await self._save_head(fields=[self.BLACKBOARD_FIELD])

        self.status = new_status
        await self._update_status(new_status)

    async def _execute_local_python(self):
        """Executes internal python handlers, supporting both sync and async."""
        slug = self.spell.talos_executable.executable
        handler_func = NATIVE_HANDLERS.get(slug)

        if not handler_func:
            raise NotImplementedError(f'No handler found for slug: {slug}')

        await self.logger.flush()

        try:
            if asyncio.iscoroutinefunction(handler_func):
                return_code, output_log = await handler_func(self.head_id)
            else:
                return_code, output_log = await sync_to_async(handler_func)(
                    self.head_id
                )
        except Exception as e:
            self.head.application_log = f'Native Handler Exception: {str(e)}'
            await self._save_head(fields=[self.APPLICATION_LOG_FIELD])
            self.status = HydraHeadStatus.FAILED
            return

        self.head.application_log = output_log
        await self._save_head(fields=[self.APPLICATION_LOG_FIELD])

        new_status = (
            HydraHeadStatus.SUCCESS
            if return_code == 200
            else HydraHeadStatus.FAILED
        )
        await self._update_status(new_status)

    def _load_head_sync(self):
        self.head = HydraHead.objects.select_related(
            'spell',
            'spell__talos_executable',
            'target',
            'spawn',
            'spawn__environment',
            'node',
            'node__environment',
        ).get(id=self.head_id)
        self.spell = self.head.spell

    def _log_info(self, message: str):
        if self.verbose_logging:
            logger.info(message)

    async def _save_head(self, fields: List[str]):
        """Async wrapper for saving specific fields."""
        try:
            await sync_to_async(self.head.save)(update_fields=fields)
        except Exception as e:
            logger.error(
                f'Failed to save Head {self.head.id} fields {fields}: {e}'
            )

    async def _update_status(self, status_id: int):
        self.head.status_id = status_id
        await self._save_head(fields=[self.STATUS_FIELD])

    async def _preflight(self):
        self.head.execution_log = self.LOG_START_MESSAGE
        await self._save_head(fields=[self.EXECUTION_LOG_FIELD])

    def _handle_fatal_error_sync(self, e: Exception):
        """Synchronous fallback for loop crashes."""
        logger.error(f'Critical Caster Failure: {e}')
        trace = traceback.format_exc()
        if self.head:
            try:
                self.head.execution_log += (
                    f'\n[FATAL SYSTEM ERROR]\n{str(e)}\n{trace}\n'
                )
                self.head.status_id = HydraHeadStatus.FAILED
                self.head.save(update_fields=['execution_log', 'status'])
            except Exception as db_err:
                logger.error(
                    f'Double Fault: Failed to write error to DB: {db_err}'
                )

    async def _handle_fatal_error(self, e: Exception):
        """Async error handler for pipeline logic."""
        logger.error(f'Pipeline execution failed: {e}')
        error_msg = f'\n[FATAL] Pipeline Error: {e}\n'
        if self.logger:
            try:
                await self.logger.write_immediate(error_msg)
            except Exception:
                pass
        if self.head:
            try:
                await self._update_status(HydraHeadStatus.FAILED)
            except Exception:
                pass
        self.status = HydraHeadStatus.FAILED
