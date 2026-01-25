import asyncio
import logging
import sys
import time
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


HANDLERS = dict(
    deploy_release_test=deploy_release_test,
    update_version_metadata=update_version_metadata,
)


class GenericSpellCaster:
    """
    The Orchestrator for Talos Spells.

    Architecture:
    -------------
    This class is the bridge between Django (Synchronous DB) and Talos Agent (Async IO).
    It initializes in Sync mode but immediately promotes to an Async Event Loop
    in `execute()`.

    All internal logic (pipelines, logging, status updates) is strictly Async.
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

    # Logging Tuning
    LOG_BUFFER_SIZE = 50  # Lines
    LOG_FLUSH_INTERVAL = 1.0  # Seconds

    def __init__(self, head_id: uuid.UUID):
        self.head_id = head_id
        self.verbose_logging = True

        # Runtime State
        self.head: Optional[HydraHead] = None
        self.spell = None
        self.status = self.STATUS_CREATED

        # Log Buffering State
        self._log_buffer: List[str] = []
        self._last_log_save: float = 0.0

    def execute(self):
        """
        Public Synchronous Entry Point.
        Promotes execution to a dedicated AsyncIO Event Loop.
        """
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(
                asyncio.WindowsProactorEventLoopPolicy()
            )

        try:
            asyncio.run(self._execute_async())
        except Exception as e:
            # Fallback for catastrophic loop failures
            logger.error(f'Critical Caster Failure: {e}')
            # We can't easily save to DB here if the loop crashed,
            # but we trust _execute_async handles its own errors.

    async def _execute_async(self):
        """The Main Async Event Loop."""
        try:
            await self._load_head()
            await self._preflight()
            await self._cast_spell()
        except Exception as e:
            await self._handle_fatal_error(e)

    # =========================================================================
    # Core Logic
    # =========================================================================

    async def _cast_spell(self):
        """Orchestrates the spell lifecycle."""
        self._log_info(f'Launching {self.spell.name}')
        await self._update_status(HydraHeadStatus.RUNNING)

        # 1. Execute (Route to Python or Subprocess)
        await self._executable_router()

        # 2. Post-Processing (if successful)
        if self.status not in self.STATUSES_WHICH_HALT:
            self._log_info(f'Post Processing {self.spell.name}')
            self.status = self.STATUS_POST_PROCESSING
            # (Add future async post-processing hooks here)

        # 3. Completion
        if self.status not in self.STATUSES_WHICH_HALT:
            self.status = self.STATUS_COMPLETE
            await self._update_status(HydraHeadStatus.SUCCESS)
            await self._append_to_log('\n[EXIT] Success.\n')

        self._log_info(f'{self.spell.name} END OF LINE')

    async def _executable_router(self):
        """Routes execution to Internal Python or External Process."""
        if self.spell.talos_executable.internal:
            self._log_info(f'Internal Python Route {self.spell.name}')
            await self._execute_local_python()
        else:
            self._log_info(f'POpen Route {self.spell.name}')
            await self._execute_local_popen()

    async def _execute_local_popen(self):
        """
        Runs an external executable using the Unified Talos Agent Engine.
        """
        # 1. Prepare Arguments
        cmd_list = await sync_to_async(spell_switches_and_arguments)(
            self.spell.id
        )
        full_cmd = [self.spell.talos_executable.executable] + cmd_list
        log_path = self.spell.talos_executable.log

        # 2. Log Start
        await self._append_to_log(f'[CMD] {" ".join(full_cmd)}\n')

        # 3. Run Pipeline
        # We pass self._stream_callback directly to the engine
        exit_code = await run_hydra_pipeline(
            full_cmd, log_path, self._stream_callback
        )

        # 4. Final Flush
        await self._flush_logs()

        # 5. Handle Result
        if exit_code != 0:
            await self._append_to_log(
                f'\n[EXIT] Process failed with code {exit_code}\n'
            )
            self.status = self.STATUS_FAILED
            await self._update_status(HydraHeadStatus.FAILED)

    async def _execute_local_python(self):
        """
        Runs a legacy synchronous Python handler in a non-blocking way.
        """
        slug = self.spell.talos_executable.executable
        if slug not in HANDLERS:
            raise NotImplementedError(f'No handler found for slug: {slug}')

        handler_func = HANDLERS[slug]

        self._log_info('Handler Start')

        # Wrap the sync handler in sync_to_async to prevent blocking the loop
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

        # Update Logs and Status
        self.head.spell_log = output_log
        await self._save_head(fields=[self.SPELL_LOG_FIELD])

        new_status = (
            HydraHeadStatus.SUCCESS
            if return_code == HANDLER_SUCCESS_CODE
            else HydraHeadStatus.FAILED
        )
        await self._update_status(new_status)

    # =========================================================================
    # Logging & Buffering
    # =========================================================================

    async def _stream_callback(self, text: str):
        """
        The callback passed to Talos Agent.
        Buffers logs and flushes periodically to DB.
        """
        self._log_buffer.append(text)

        now = time.time()
        should_flush = (
            len(self._log_buffer) > self.LOG_BUFFER_SIZE
            or (now - self._last_log_save) > self.LOG_FLUSH_INTERVAL
        )

        if should_flush:
            await self._flush_logs()

    async def _flush_logs(self):
        """Writes the buffer to Postgres."""
        if not self._log_buffer:
            return

        chunk = ''.join(self._log_buffer)
        # Append to the existing log in memory
        self.head.execution_log += chunk

        await self._save_head(fields=[self.EXECUTION_LOG_FIELD])

        self._log_buffer.clear()
        self._last_log_save = time.time()

    async def _append_to_log(self, text: str):
        """Immediate write to execution log (bypasses buffer for events)."""
        await self._flush_logs()  # Clear buffer first to maintain order
        self.head.execution_log += text
        await self._save_head(fields=[self.EXECUTION_LOG_FIELD])

    # =========================================================================
    # DB & Helpers
    # =========================================================================

    async def _load_head(self):
        """Loads HydraHead and Spell in an async context."""
        self.head = await HydraHead.objects.select_related(
            'spell', 'spell__talos_executable'
        ).aget(id=self.head_id)
        self.spell = self.head.spell

    async def _preflight(self):
        self._log_info(f'Preflight for {self.spell.name}')
        self.head.execution_log = self.LOG_START_MESSAGE
        await self._save_head(fields=[self.EXECUTION_LOG_FIELD])

    async def _update_status(self, status_id: int):
        self.head.status_id = status_id
        await self._save_head(fields=[self.STATUS_FIELD])

    async def _save_head(self, fields: List[str]):
        """Async wrapper for saving the model."""
        # Django 4.1+ has .asave(), but sync_to_async is safer for older versions/compat
        await sync_to_async(self.head.save)(update_fields=fields)

    async def _handle_fatal_error(self, e: Exception):
        logger.error(f'Pipeline execution failed: {e}')
        if self.head:
            self.head.execution_log += f'\n[FATAL] Pipeline Error: {e}\n'
            # Try to save the error to the log
            try:
                await self._save_head(fields=[self.EXECUTION_LOG_FIELD])
                await self._update_status(HydraHeadStatus.FAILED)
            except:
                pass  # DB might be down
        self.status = self.STATUS_FAILED

    def _log_info(self, message: str):
        if self.verbose_logging:
            logger.info(message)
