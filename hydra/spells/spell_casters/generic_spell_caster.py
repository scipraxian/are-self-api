import asyncio
import logging
import sys
import time
import traceback
import uuid
from typing import List, Optional

from asgiref.sync import sync_to_async

from hydra.models import HydraHead, HydraHeadStatus
from hydra.spells.spell_casters.spell_handlers.deployment_handler import (
    deploy_release_test,
)
from hydra.spells.spell_casters.spell_handlers.spell_handler_codes import (
    HANDLER_SUCCESS_CODE,
)
from hydra.spells.spell_casters.spell_handlers.version_metadata_handler import (
    update_version_metadata,
)
from hydra.spells.spell_casters.switches_and_arguments import (
    spell_switches_and_arguments,
)
from talos_agent.talos_agent import run_hydra_pipeline

logger = logging.getLogger(__name__)

# Native Python Handlers (Synchronous)
NATIVE_HANDLERS = dict(
    deploy_release_test=deploy_release_test,
    update_version_metadata=update_version_metadata,
)


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
        """Appends to Execution Log (Stdout/System)."""
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

        # Merge buffers into the head object
        if self.exec_buffer:
            self.head.execution_log += ''.join(self.exec_buffer)
            self.exec_buffer.clear()

        if self.spell_buffer:
            self.head.spell_log += ''.join(self.spell_buffer)
            self.spell_buffer.clear()

        await self._save_to_db()
        self._last_flush_time = time.time()

    async def _save_to_db(self):
        """
        Saves logs AND checks for ABORT signals from the Manager.
        """
        try:
            await sync_to_async(self.head.save)(
                update_fields=['execution_log', 'spell_log']
            )

            # --- THE SUICIDE PACT ---
            # Refresh status to check for remote kill signal
            await sync_to_async(self.head.refresh_from_db)(fields=['status'])
            if self.head.status_id == HydraHeadStatus.ABORTED:
                raise ConnectionAbortedError('Hydra Head Aborted by User')

        except ConnectionAbortedError:
            # Re-raise to stop the pipeline
            raise
        except Exception as e:
            logger.error(
                f'Failed to save execution log for Head {self.head.id}: {e}'
            )


class GenericSpellCaster:
    """
    The Orchestrator for Talos Spells.
    """

    LOG_START_MESSAGE = 'Starting spell execution.\n'

    # Status Constants
    STATUS_CREATED = 1
    STATUS_RUNNING = 2
    STATUS_STREAMING_LOGS = 3
    STATUS_POST_PROCESSING = 4
    STATUS_COMPLETE = 5
    STATUS_FAILED = 6
    STATUS_ABORTED = 7

    STATUSES_WHICH_HALT = [STATUS_FAILED, STATUS_ABORTED]

    # DB Field Names
    EXECUTION_LOG_FIELD = 'execution_log'
    SPELL_LOG_FIELD = 'spell_log'
    STATUS_FIELD = 'status'

    def __init__(self, head_id: uuid.UUID):
        self.head_id = head_id
        self.verbose_logging = True

        # Runtime State
        self.head: Optional[HydraHead] = None
        self.spell = None
        self.status = self.STATUS_CREATED
        self.logger: Optional[AsyncLogManager] = None

    # =========================================================================
    # Entry Points
    # =========================================================================

    def execute(self):
        """
        Public Synchronous Entry Point.
        """
        logger.info(f'Initializing execution for Head ID: {self.head_id}')

        # 1. Load State Synchronously (Safety Net)
        try:
            self._load_head_sync()
        except Exception as e:
            logger.error(f'FATAL: Could not load HydraHead {self.head_id}: {e}')
            return

        # 2. Configure Windows Event Loop
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(
                asyncio.WindowsProactorEventLoopPolicy()
            )

        # 3. Enter Async Mode
        try:
            asyncio.run(self._execute_async())
        except Exception as e:
            self._handle_fatal_error_sync(e)

    async def _execute_async(self):
        """The Main Async Event Loop."""
        try:
            self.logger = AsyncLogManager(self.head)
            await self._preflight()

            # Launch the Spell AND the Abort Monitor concurrently
            spell_task = asyncio.create_task(self._cast_spell())
            monitor_task = asyncio.create_task(self._monitor_abort_signal())

            # Wait for the spell to finish OR the monitor to kill it
            done, pending = await asyncio.wait(
                [spell_task, monitor_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cleanup
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Check if the monitor killed us
            if monitor_task in done:
                try:
                    # If monitor finished, it means it raised an Abort exception
                    exc = monitor_task.exception()
                    if exc:
                        raise exc
                except ConnectionAbortedError:
                    logger.warning(
                        f'Head {self.head_id} execution aborted by user.'
                    )
                    return  # Exit gracefully

            # If spell finished first, check for its errors
            if spell_task in done:
                exc = spell_task.exception()
                if exc:
                    raise exc

        except ConnectionAbortedError:
            pass  # Graceful exit
        except Exception as e:
            await self._handle_fatal_error(e)

    # =========================================================================
    # Internal Logic
    # =========================================================================

    async def _monitor_abort_signal(self):
        """
        Background task that checks DB status every second.
        Raises ConnectionAbortedError if user clicked 'Terminate'.
        """
        while True:
            await asyncio.sleep(1.0)

            # Use sync_to_async to safely hit DB
            await sync_to_async(self.head.refresh_from_db)(fields=['status'])

            if self.head.status_id == HydraHeadStatus.ABORTED:
                # Log the kill
                if self.logger:
                    await self.logger.write_immediate(
                        '\n[ABORT] Received Kill Signal from Hydra.\n'
                    )

                # This exception will cancel the _cast_spell task
                raise ConnectionAbortedError('Aborted by User')

    async def _cast_spell(self):
        self._log_info(f'Launching {self.spell.name}')
        await self._update_status(HydraHeadStatus.RUNNING)

        await self._executable_router()

        if self.status not in self.STATUSES_WHICH_HALT:
            self.status = self.STATUS_COMPLETE
            await self._update_status(HydraHeadStatus.SUCCESS)

    async def _executable_router(self):
        if self.spell.talos_executable.internal:
            await self._execute_local_python()
        else:
            await self._execute_local_popen()

    async def _execute_local_popen(self):
        # 1. Prepare Arguments
        cmd_list = await sync_to_async(spell_switches_and_arguments)(
            self.spell.id
        )
        full_cmd = [self.spell.talos_executable.executable] + cmd_list
        log_path = self.spell.talos_executable.log

        # 2. Log Start
        await self.logger.write_immediate(f'[CMD] {" ".join(full_cmd)}\n')
        self.status = self.STATUS_STREAMING_LOGS

        # 3. Run Pipeline
        logger.info(f'Running Pipeline for: {full_cmd}')

        # CRITICAL UPDATE: Pass two separate callbacks
        # 1. self.logger.append -> Goes to execution_log (Stdout)
        # 2. self.logger.append_spell -> Goes to spell_log (File)
        exit_code = await run_hydra_pipeline(
            full_cmd,
            log_path,
            self.logger.append,
            self.logger.append_spell,
        )
        logger.info(f'Pipeline finished with code: {exit_code}')

        # 4. Final Flush & Result
        if exit_code == 0:
            await self.logger.write_immediate('\n[EXIT] Success.\n')
        else:
            await self.logger.write_immediate(
                f'\n[EXIT] Process failed with code {exit_code}\n'
            )
            self.status = self.STATUS_FAILED
            await self._update_status(HydraHeadStatus.FAILED)

    async def _execute_local_python(self):
        slug = self.spell.talos_executable.executable
        if slug not in NATIVE_HANDLERS:
            raise NotImplementedError(f'No handler found for slug: {slug}')

        handler_func = NATIVE_HANDLERS[slug]
        await self.logger.flush()

        try:
            return_code, output_log = await sync_to_async(handler_func)(
                self.head_id
            )
        except Exception as e:
            self.head.spell_log = f'Native Handler Exception: {str(e)}'
            await self._save_head(fields=[self.SPELL_LOG_FIELD])
            self.status = self.STATUS_FAILED
            await self._update_status(HydraHeadStatus.FAILED)
            return

        self.head.spell_log = output_log
        await self._save_head(fields=[self.SPELL_LOG_FIELD])

        new_status = (
            HydraHeadStatus.SUCCESS
            if return_code == HANDLER_SUCCESS_CODE
            else HydraHeadStatus.FAILED
        )
        await self._update_status(new_status)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _load_head_sync(self):
        self.head = HydraHead.objects.select_related(
            'spell', 'spell__talos_executable'
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

    # =========================================================================
    # Error Handling
    # =========================================================================

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

        self.status = self.STATUS_FAILED
