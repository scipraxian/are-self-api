import logging
import subprocess
import time
import uuid
from os.path import exists, getmtime
from time import sleep

from environments.models import TalosExecutable
from hydra.models import HydraHead, HydraHeadStatus
from hydra.spells.distributor import distribute_build_native
from hydra.spells.version_stamper import version_stamp_native

logger = logging.getLogger(__name__)

HANDLERS = dict(
    distribute_fleet=distribute_build_native,
    version_stamper=version_stamp_native,
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

    def __init__(self, head_id: uuid):  # todo: callback
        self.status = self.STATUS_CREATED
        self.head_id = head_id

        self.head = HydraHead.objects.get(id=head_id)
        self.spell = self.head.spell
        self.running_log = []
        self._preflight()
        self._cast_spell()

    def _debug_log(self, message: str):
        # TODO: build nice message?
        logger.debug(message)

    def _init_running_log(self):
        """Create the log array."""
        self.running_log = [self.LOG_START_MESSAGE, ]

    def _resolve_switches(self):
        """Resolve the switches for the spell.

        Note: We are expecting no composite flags, one flag/value per switch.
        TODO: resolve switch templates.
        """
        switch_string = ''

        for switch in self.spell.talos_executable.switches.all():
            switch_string += ' ' + switch.flag
            if switch.value:
                switch_string += switch.value

        for switch in self.spell.switches.all():
            switch_string += ' ' + switch.flag
            if switch.value:
                switch_string += switch.value

        self.switch_string = switch_string.strip()

    def _resolve_arguments(self):
        """Resolve the arguments for the spell."""
        ordered_arguments_string = ''

        for assignment in self.spell.talos_executable.talosexecutableargumentassignment_set.all():
            ordered_arguments_string += ' ' + assignment.argument.argument

        for assignment in self.spell.hydraspellargumentassignment_set.all():
            ordered_arguments_string += ' ' + assignment.argument.argument

        self.ordered_arguments_string = ordered_arguments_string.strip()

    def _update_head_status(self, status_id: int):
        self.head.status_id = status_id
        self.head.save(update_fields=['status'])

    def _preflight(self):
        self._debug_log(f"Preflight for {self.spell.name}")
        self._init_running_log()
        self._resolve_switches()
        self._resolve_arguments()

    def _get_command(self):
        return f'{self.spell.talos_executable.executable} {self.ordered_arguments_string} {self.switch_string}'

    def _post_head_log(self):
        """Save the log to the DB. TODO: do this asynchronously, it may block."""
        self._debug_log(f"Post Log to DB {self.spell.talos_executable.log}")
        self.head.spell_log = "".join(self.running_log)

    def _block_for_log_file(self):
        """
        Blocks execution until a FRESH log file appears or timeout occurs.
        Prevents attaching to stale log files from previous runs.
        """
        if not self.spell.talos_executable.log:
            logger.warning('No log file defined in context. Skipping block.')
            return

        # Default to now if launch_time wasn't set by the executor (failsafe)
        launch_time = getattr(self, 'launch_time', time.time())

        max_retries = 100
        retries = 0

        while retries < max_retries:
            # 1. Process Watchdog: Did it die instantly?
            if self.running_subprocess and self.running_subprocess.poll() is not None:
                logger.error(f'Process died (Exit {self.running_subprocess.returncode}) before log appeared.')
                self._update_head_status(HydraHeadStatus.FAILED)
                self.status = self.STATUS_FAILED
                return

            # 2. File Check
            if exists(self.spell.talos_executable.log):
                try:  # TODO: tighten this try/except.
                    # Windows 'getctime' is creation, 'getmtime' is modify.
                    # We check mtime to be safe.
                    file_mtime = getmtime(self.spell.talos_executable.log)

                    # Freshness Test: Is file newer than launch time? (with 1s buffer)
                    if file_mtime >= (launch_time - 1.0):
                        self._debug_log(f'Locked onto fresh log file: {self.spell.talos_executable.log}')
                        return
                    else:
                        # Log exists, but it's old. Wait for UE to overwrite it.
                        if retries % 5 == 0:
                            self._debug_log(f'Ignoring stale log (Mtime: {file_mtime} < Launch: {launch_time})')
                except OSError:
                    pass  # File locked by OS, retry next tick.

            sleep(0.5)
            retries += 1

        # 3. Timeout
        logger.error(f'Timed out waiting for log file: {self.spell.talos_executable.log}')
        self.status = self.STATUS_FAILED

    def _stream_log_file(self):
        """While running_subprocess, read the entire log each loop and post to the DB."""
        if self.status in self.STATUSES_WHICH_HALT: return
        self.status = self.STATUS_STREAMING_LOGS
        with open(self.spell.talos_executable.log, 'r', encoding='utf-8', errors='replace') as local_log:
            while self.running_subprocess.poll() is not None and self.status not in self.STATUSES_WHICH_HALT:
                self.running_log = local_log.read()
                self._post_head_log()
                # TODO: strongly consider a hook here, the agent would know if it updated.
                sleep(0.1)

    def _log_router(self):
        if self.spell.talos_executable_id != TalosExecutable.INTERNAL_FUNCTION:
            self._debug_log(f'Blocking for Log {self.spell.talos_executable.log}')
            self._block_for_log_file()
            self._debug_log(f'Streaming Log {self.spell.talos_executable.log}')
            self._stream_log_file()
        else:
            self._debug_log('Internal function does not stream logs?')

    def _execute_local_python(self):
        # Safety check for missing handlers
        if self.spell.talos_executable.executable not in HANDLERS:
            raise NotImplementedError(f"No handler found for slug: {self.spell.executable.slug}")

        handler = HANDLERS[self.spell.talos_executable.executable]

        # TODO: consider an async option here (no return).
        output_log = 'attempting'
        return_code = 1
        try:
            return_code, output_log = handler(self.head_id)
        except Exception as e:
            self.head.spell_log = f'Native Handler Exception: {str(e)}'
            self._update_head_status(HydraHeadStatus.FAILED)
        self.head.spell_log = output_log
        self.head.status_id = (HydraHeadStatus.SUCCESS
                               if return_code == 0 else HydraHeadStatus.FAILED)
        self.head.save()

    def _execute_local_popen(self):
        """The default method for executing spells."""
        execution_command = self._get_command()
        try:
            self.running_subprocess = subprocess.Popen(
                execution_command, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            # TODO: narrow exception type
            raise RuntimeError(f'Failed to launch spell execution: {e}')

    def _executable_router(self):
        if self.spell.talos_executable_id == TalosExecutable.INTERNAL_FUNCTION:
            self._execute_local_python()
        else:
            self._execute_local_popen()

    def _post_processor(self):
        """Run post processing steps after streaming logs."""
        self.status = self.STATUS_POST_PROCESSING

    def _cast_spell(self):
        self._debug_log(f'Launching {self.spell.name}')
        self._update_head_status(HydraHeadStatus.RUNNING)
        self._executable_router()
        self._debug_log(f'Logging {self.spell.name}')
        self._log_router()
        self._debug_log(f'Post Processing {self.spell.name}')
        self._post_processor()
        self._debug_log(f'Clean Up {self.spell.name}')
        if self.running_subprocess:
            self.running_subprocess.kill()
        if self.status not in self.STATUSES_WHICH_HALT:
            self.status = self.STATUS_COMPLETE
        self._debug_log(f'{self.spell.name} END OF LINE')
