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

NATIVE_HANDLERS = dict(
    deploy_release_test=deploy_release_test,
    update_version_metadata=update_version_metadata,
)


class AsyncLogManager:
    """
    Handles buffered log writes to the Database with async safety.
    """

    def __init__(self, head: HydraHead, flush_size=50, flush_interval=1.0):
        self.head = head
        self.buffer: List[str] = []
        self._lock = asyncio.Lock()
        self._last_flush_time = time.time()
        self._flush_size = flush_size
        self._flush_interval = flush_interval

    async def append(self, text: str):
        async with self._lock:
            self.buffer.append(text)
            if self._should_flush():
                await self._flush_unsafe()

    async def write_immediate(self, text: str):
        """Writes to DB immediately (bypassing buffer) and logs to system."""
        logger.info(f'[HEAD {self.head.id}] {text.strip()}')

        async with self._lock:
            await self._flush_unsafe()
            self.head.execution_log += text
            await self._save_to_db()

    async def flush(self):
        async with self._lock:
            await self._flush_unsafe()

    def _should_flush(self) -> bool:
        return (
            len(self.buffer) > self._flush_size
            or (time.time() - self._last_flush_time) > self._flush_interval
        )

    async def _flush_unsafe(self):
        if not self.buffer:
            return

        chunk = ''.join(self.buffer)
        self.head.execution_log += chunk
        await self._save_to_db()
        self.buffer.clear()
        self._last_flush_time = time.time()

    async def _save_to_db(self):
        try:
            await sync_to_async(self.head.save)(update_fields=['execution_log'])
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

            # Launch tasks concurrently
            spell_task = asyncio.create_task(self._cast_spell())
            monitor_task = asyncio.create_task(self._monitor_abort_signal())

            # Wait for either completion or abort
            done, pending = await asyncio.wait(
                [spell_task, monitor_task], return_when=asyncio.FIRST_COMPLETED
            )

            # --- CLEANUP / CANCELLATION ---
            for task in pending:
                task.cancel()  # <--- Sends CancelledError to run_hydra_pipeline
                try:
                    await task  # <--- Waits for talos_agent to finish killing the process
                except asyncio.CancelledError:
                    pass

            if monitor_task in done:
                try:
                    monitor_task.result()  # Will raise ConnectionAbortedError if aborted
                except ConnectionAbortedError:
                    logger.warning(
                        f'Head {self.head_id} execution aborted by user.'
                    )
                    return  # Exit gracefully

            if spell_task in done:
                # Check if the spell crashed on its own
                exc = spell_task.exception()
                if exc:
                    raise exc

        except ConnectionAbortedError:
            pass
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
        cmd_list = await sync_to_async(spell_switches_and_arguments)(
            self.spell.id
        )
        full_cmd = [self.spell.talos_executable.executable] + cmd_list
        log_path = self.spell.talos_executable.log

        await self.logger.write_immediate(f'[CMD] {" ".join(full_cmd)}\n')
        self.status = self.STATUS_STREAMING_LOGS

        logger.info(f'Running Pipeline for: {full_cmd}')

        # NOTE: run_hydra_pipeline is awaited here.
        # If _monitor_abort_signal raises exception, this task gets Cancelled.
        # asyncio.CancelledError will bubble through here.
        # Python's asyncio subprocess usually leaves orphans on cancellation.
        # However, since we can't touch talos_agent right now, we rely on
        # the OS cleaning up or the fact that we stop tracking it.
        # Ideally, run_hydra_pipeline handles cancellation by killing the proc.

        exit_code = await run_hydra_pipeline(
            full_cmd,
            log_path,
            self.logger.append,
        )
        logger.info(f'Pipeline finished with code: {exit_code}')

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
