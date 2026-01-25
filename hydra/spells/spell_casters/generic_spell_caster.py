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

# Legacy synchronous handlers
HANDLERS = dict(
    deploy_release_test=deploy_release_test,
    update_version_metadata=update_version_metadata,
)


class AsyncLogManager:
    """
    Handles buffered log writes to the Database with async safety.
    Prevents race conditions between stream callbacks and main thread events.
    """

    def __init__(self, head: HydraHead, flush_size=50, flush_interval=1.0):
        self.head = head
        self.buffer: List[str] = []
        self._lock = asyncio.Lock()
        self._last_flush_time = time.time()
        self._flush_size = flush_size
        self._flush_interval = flush_interval

    async def append(self, text: str):
        """Buffers text and auto-flushes if thresholds are met."""
        async with self._lock:
            self.buffer.append(text)
            if self._should_flush():
                await self._flush_unsafe()

    async def write_immediate(self, text: str):
        """Bypasses buffer for critical events (Start/Stop/Error)."""
        async with self._lock:
            # Flush existing buffer first to maintain order
            await self._flush_unsafe()
            self.head.execution_log += text
            await self._save_to_db()

    async def flush(self):
        """Public thread-safe flush."""
        async with self._lock:
            await self._flush_unsafe()

    def _should_flush(self) -> bool:
        """Internal check for flush thresholds."""
        return (
            len(self.buffer) > self._flush_size
            or (time.time() - self._last_flush_time) > self._flush_interval
        )

    async def _flush_unsafe(self):
        """Internal flush logic (Lock must be held by caller)."""
        if not self.buffer:
            return

        chunk = ''.join(self.buffer)
        self.head.execution_log += chunk
        await self._save_to_db()

        self.buffer.clear()
        self._last_flush_time = time.time()

    async def _save_to_db(self):
        """
        Persist to Postgres.
        NOTE: Assumes single-writer per HydraHead.
        Concurrent modifications would require F() expressions.
        """
        await sync_to_async(self.head.save)(update_fields=['execution_log'])


class GenericSpellCaster:
    """
    The Orchestrator for Talos Spells.
    Promotes execution to an AsyncIO Event Loop and manages the lifecycle.
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

    def execute(self):
        """
        Public Synchronous Entry Point.
        """
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(
                asyncio.WindowsProactorEventLoopPolicy()
            )

        try:
            asyncio.run(self._execute_async())
        except Exception as e:
            logger.error(f'Critical Caster Failure: {e}')

    async def _execute_async(self):
        """The Main Async Event Loop."""
        try:
            await self._load_head()
            self.logger = AsyncLogManager(self.head)

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

        # 1. Execute
        await self._executable_router()

        # 2. Post-Processing
        if self.status not in self.STATUSES_WHICH_HALT:
            self._log_info(f'Post Processing {self.spell.name}')
            self.status = self.STATUS_POST_PROCESSING

        # 3. Completion
        if self.status not in self.STATUSES_WHICH_HALT:
            self.status = self.STATUS_COMPLETE
            await self._update_status(HydraHeadStatus.SUCCESS)

        self._log_info(f'{self.spell.name} END OF LINE')

    async def _executable_router(self):
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
        await self.logger.write_immediate(f'[CMD] {" ".join(full_cmd)}\n')
        self.status = self.STATUS_STREAMING_LOGS

        # 3. Run Pipeline
        exit_code = await run_hydra_pipeline(
            full_cmd,
            log_path,
            self.logger.append,  # Pass the buffer append method directly
        )

        # 4. Final Flush & Result Logging
        if exit_code == 0:
            await self.logger.write_immediate('\n[EXIT] Success.\n')
        else:
            await self.logger.write_immediate(
                f'\n[EXIT] Process failed with code {exit_code}\n'
            )
            self.status = self.STATUS_FAILED
            await self._update_status(HydraHeadStatus.FAILED)

    async def _execute_local_python(self):
        """
        Runs a legacy synchronous Python handler non-blocking.
        """
        slug = self.spell.talos_executable.executable
        if slug not in HANDLERS:
            raise NotImplementedError(f'No handler found for slug: {slug}')

        handler_func = HANDLERS[slug]
        self._log_info('Handler Start')

        # Ensure any pending logs are flushed before handing off
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
    # Helpers
    # =========================================================================

    async def _load_head(self):
        self.head = await HydraHead.objects.select_related(
            'spell', 'spell__talos_executable'
        ).aget(id=self.head_id)
        self.spell = self.head.spell

    async def _preflight(self):
        self._log_info(f'Preflight for {self.spell.name}')
        # Direct write to initialize log
        self.head.execution_log = self.LOG_START_MESSAGE
        await self._save_head(fields=[self.EXECUTION_LOG_FIELD])

    async def _update_status(self, status_id: int):
        self.head.status_id = status_id
        await self._save_head(fields=[self.STATUS_FIELD])

    async def _save_head(self, fields: List[str]):
        await sync_to_async(self.head.save)(update_fields=fields)

    async def _handle_fatal_error(self, e: Exception):
        logger.error(f'Pipeline execution failed: {e}')

        # Use logger if available (ensures proper ordering)
        if self.logger:
            try:
                await self.logger.write_immediate(
                    f'\n[FATAL] Pipeline Error: {e}\n'
                )
            except Exception:
                pass  # Logger/DB might be down

        # Update status
        if self.head:
            try:
                await self._update_status(HydraHeadStatus.FAILED)
            except Exception:
                pass  # DB might be down

        self.status = self.STATUS_FAILED

    def _log_info(self, message: str):
        if self.verbose_logging:
            logger.info(message)
