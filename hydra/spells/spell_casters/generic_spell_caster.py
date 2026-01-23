import asyncio
import logging
import time
import uuid

from hydra.models import HydraHead, HydraHeadStatus
from hydra.process_runner.log_monitor import AsyncLogMonitor
from hydra.process_runner.process_runner import AsyncProcessRunner
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
    spaces_have_quotes,
    spell_switches_and_arguments,
)

logger = logging.getLogger(__name__)


HANDLERS = dict(
    deploy_release_test=deploy_release_test,
    update_version_metadata=update_version_metadata,
)


class GenericSpellCaster(object):
    LOG_START_MESSAGE = 'Starting spell execution.'

    STATUS_CREATED = 1
    STATUS_RUNNING = 2
    STATUS_STREAMING_LOGS = 3
    STATUS_POST_PROCESSING = 4
    STATUS_COMPLETE = 5
    STATUS_FAILED = 6
    STATUS_ABORTED = 7

    STATUSES_WHICH_HALT = [STATUS_FAILED, STATUS_ABORTED]

    HEAD_STATUS_FIELD_NAME = 'status'

    EXECUTION_LOG_FIELD_NAME = 'execution_log'
    SPELL_LOG_FIELD_NAME = 'spell_log'

    def __init__(self, head_id: uuid.UUID):
        self._debug_log('Created Generic Spell Caster')
        self.status = self.STATUS_CREATED
        self.head_id = head_id
        self.running_subprocess = None
        self.running_log = []
        self._start_head()

    def _start_head(self):
        self.head = HydraHead.objects.get(id=self.head_id)
        self.spell = self.head.spell
        self._preflight()
        self._cast_spell()

    def _debug_log(self, message: str):
        # TODO: build nice message?
        logger.info(message)

    def _init_running_log(self):
        """Create the log array."""
        self.running_log = [
            self.LOG_START_MESSAGE,
        ]

    def _update_head_status(self, status_id: int):
        self.head.status_id = status_id
        self.head.save(update_fields=['status'])

    def _preflight(self):
        self._debug_log(f'Preflight for {self.spell.name}')
        self._init_running_log()

    def _post_head_log(self):
        """Save the log to the DB. TODO: do this asynchronously, it may block."""
        self._debug_log(f'Post Log to DB {self.spell.talos_executable.log}')
        self.head.spell_log = ''.join(self.running_log)
        self.head.save(update_fields=[self.SPELL_LOG_FIELD_NAME])

    def _execute_local_python(self):
        if self.spell.talos_executable.executable not in HANDLERS:
            raise NotImplementedError(
                f'No handler found for slug: {self.spell.executable.slug}'
            )
        handler = HANDLERS[self.spell.talos_executable.executable]
        # TODO: consider an async option here (no return).
        output_log = 'attempting'
        return_code = 1
        try:
            self._debug_log('Handler Start')
            return_code, output_log = handler(self.head_id)
            self._debug_log(f'Handler return code is {return_code}')
        except Exception as e:
            self.head.spell_log = f'Native Handler Exception: {str(e)}'
            self._update_head_status(HydraHeadStatus.FAILED)
        self.head.spell_log = output_log
        head_status_id = (
            HydraHeadStatus.SUCCESS
            if return_code == HANDLER_SUCCESS_CODE
            else HydraHeadStatus.FAILED
        )
        self.head.status_id = head_status_id
        self.head.save()

    async def _watch_process(self, runner: AsyncProcessRunner):
        """Drains STDOUT/STDERR from the process runner to the DB."""
        buffer = []
        last_save = time.time()
        async for line in runner.stream_output():
            buffer.append(line)
            if len(buffer) > 20 or (time.time() - last_save) > 1.0:
                self.head.execution_log += ''.join(buffer)
                self.head.save(update_fields=[self.EXECUTION_LOG_FIELD_NAME])
                buffer = []
                last_save = time.time()
        if buffer:
            self.head.execution_log += ''.join(buffer)
            self.head.save(update_fields=[self.EXECUTION_LOG_FIELD_NAME])
        return await runner.wait()

    async def _watch_monitor(
        self, monitor: AsyncLogMonitor, runner: AsyncProcessRunner
    ):
        """Polls the log file for changes."""
        while True:
            lines = await monitor.check_for_lines()
            if lines:
                self.head.spell_log += ''.join(lines)
                self.head.save(update_fields=[self.SPELL_LOG_FIELD_NAME])
            if runner.process and runner.process.returncode is not None:
                lines = await monitor.check_for_lines()
                if lines:
                    self.head.spell_log += ''.join(lines)
                    self.head.save(update_fields=[self.SPELL_LOG_FIELD_NAME])
                break
            await asyncio.sleep(0.5)

    async def _async_pipeline(self):
        """Orchestrates the concurrent execution of process and logs."""
        self.launch_time = time.time()
        cmd_string, cmd_list = spell_switches_and_arguments(self.spell.id)
        full_cmd_list = [
            spaces_have_quotes(self.spell.talos_executable.executable)
        ] + cmd_list
        self.head.execution_log += (
            f'[CMD] {cmd_string}\n[LIST] {full_cmd_list}\n'
        )
        self.head.save(update_fields=[self.EXECUTION_LOG_FIELD_NAME])

        log_path = self.spell.talos_executable.log
        log_monitor = AsyncLogMonitor(log_path) if log_path else None

        runner = AsyncProcessRunner(command=full_cmd_list)
        await runner.start()

        process_task = asyncio.create_task(self._watch_process(runner))
        monitor_task = None
        if log_monitor:
            monitor_task = asyncio.create_task(
                self._watch_monitor(log_monitor, runner)
            )

        exit_code = await process_task

        if monitor_task:
            await asyncio.sleep(1.0)  # Flush window
            if not monitor_task.done():
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

        return exit_code

    def _execute_local_popen(self):
        """
        The default method for executing spells.
        Replaced strict blocking Popen with asyncio.run(pipeline).
        """
        try:
            exit_code = asyncio.run(self._async_pipeline())

            if exit_code != 0:
                self.head.execution_log += (
                    f'\n[EXIT] Process failed with code {exit_code}\n'
                )

                self.status = self.STATUS_FAILED
                self._update_head_status(HydraHeadStatus.FAILED)
            else:
                self.head.execution_log += '\n[EXIT] Success.\n'

            self.head.save(update_fields=[self.EXECUTION_LOG_FIELD_NAME])

        except Exception as e:
            logger.error(f'Pipeline execution failed: {e}')
            self.head.execution_log += f'\n[FATAL] Pipeline Error: {e}\n'
            self.head.save(update_fields=[self.EXECUTION_LOG_FIELD_NAME])
            self.status = self.STATUS_FAILED
            self._update_head_status(HydraHeadStatus.FAILED)
            # TODO: consider not raising and just passing the failure.
            raise RuntimeError(f'Failed to launch spell execution: {e}')

    def _executable_router(self):
        """Route the execution to the appropriate method."""
        if self.spell.talos_executable.internal:
            self._debug_log(f'Internal Python Route {self.spell.name}')
            self._execute_local_python()
        else:
            self._debug_log(f'POpen Route {self.spell.name}')
            self._execute_local_popen()

    def _post_processor(self):
        """Run post processing steps after streaming logs."""
        if self.status not in self.STATUSES_WHICH_HALT:
            self.status = self.STATUS_POST_PROCESSING
        # TODO: If errors seen here, check if post processing is needed.

    def _cast_spell(self):
        self._debug_log(f'Launching {self.spell.name}')
        self._update_head_status(HydraHeadStatus.RUNNING)
        self._executable_router()
        self._debug_log(f'Post Processing {self.spell.name}')
        self._post_processor()
        self._debug_log(f'Clean Up {self.spell.name}')
        if self.running_subprocess and hasattr(self.running_subprocess, 'kill'):
            self.running_subprocess.kill()
        if self.status not in self.STATUSES_WHICH_HALT:
            self.status = self.STATUS_COMPLETE
            self._update_head_status(HydraHeadStatus.SUCCESS)
        self._debug_log(f'{self.spell.name} END OF LINE')
