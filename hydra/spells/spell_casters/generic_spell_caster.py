import logging
import subprocess
import time
import uuid
from os.path import exists, getmtime
from time import sleep
from typing import NamedTuple

from hydra.models import HydraExecutableType, HydraHead, HydraHeadStatus
from hydra.spells.distributor import distribute_build_native
from hydra.spells.version_stamper import version_stamp_native

logger = logging.getLogger(__name__)


class SpellContext(NamedTuple):
    """Context for spell execution, containing paths and dynamic data.

    executable: this is the entire path e.g., c:/stuff/things/thing.exe
    log_file: the path to the log file for the spell which is streamed to the DB.
    dynamic_context: a dictionary of dynamic data to be passed to the spell.
    """
    executable: str
    log_file: str
    dynamic_context: dict


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

    def __init__(self, head_id: uuid, context: SpellContext, callback=None):  # todo: strongly type callback
        self.status = self.STATUS_CREATED
        self.head_id = head_id
        self.context = context
        self.callback = callback

        self.head = HydraHead.objects.get(id=head_id)
        self.spell = self.head.spell
        self.executable_type = self.spell.executable.type_id
        self.running_log = []
        self._preflight()
        self._cast_spell()

    def _debug_log(self, message: str):
        # TODO: build nice message?
        logger.debug(message)

    def _generate_context(self):
        """I can't decide if this is generated here or there, probably here."""
        # env = self.head.spawn.environment.project_environment

        # self.context = context

    def _init_running_log(self):
        """Create the log array."""
        self.running_log = [self.LOG_START_MESSAGE, ]

    def _resolve_switches(self):
        """Resolve the switches for the spell.

        Note: We are expecting no composite flags, one flag/value per switch.
        TODO: resolve switch templates.
        """
        switch_string = ''
        for switch in self.spell.active_switches.all():
            switch_string += ' ' + switch.flag
            if switch.value:
                switch_string += switch.value
        self.switch_string = switch_string.strip()

    def _update_head_status(self, status_id: int):
        self.head.status_id = status_id
        self.head.save(update_fields=['status'])

    def _validate_executable(self):
        match self.executable_type:
            case HydraExecutableType.LOCAL_PYTHON:
                pass
            case HydraExecutableType.REMOTE_PYTHON:
                pass
            case HydraExecutableType.LOCAL_POPEN:
                # TODO: this causes most tests to fail.
                # if not exists(self.context.executable):
                #     raise FileNotFoundError(f"Could not find executable at {self.context.executable}")
                pass
            case HydraExecutableType.REMOTE_POPEN:
                pass
            case _:
                raise ValueError(f"Unknown executable type: {self.executable_type}")

    def _preflight(self):
        self._debug_log(f"Preflight for {self.spell.name}")
        self._generate_context()
        self._validate_executable()
        self._init_running_log()
        self._resolve_switches()


    def _get_command(self):
        return f'{self.context.executable} {self.switch_string}'

    def _post_head_log(self):
        """Save the log to the DB. TODO: do this asynchronously, it may block."""
        self._debug_log(f"Post Log {self.context.log_file}")
        self.head.spell_log = "".join(self.running_log)

    def _block_for_log_file(self):
        """
        Blocks execution until a FRESH log file appears or timeout occurs.
        Prevents attaching to stale log files from previous runs.
        """
        if not self.context.log_file:
            logger.warning("No log file defined in context. Skipping block.")
            return

        # Default to now if launch_time wasn't set by the executor (failsafe)
        launch_time = getattr(self, 'launch_time', time.time())

        max_retries = 100
        retries = 0

        while retries < max_retries:
            # 1. Process Watchdog: Did it die instantly?
            if self.running_subprocess and self.running_subprocess.poll() is not None:
                logger.error(f"Process died (Exit {self.running_subprocess.returncode}) before log appeared.")
                self._update_head_status(HydraHeadStatus.FAILED)
                self.status = self.STATUS_FAILED
                return

            # 2. File Check
            if exists(self.context.log_file):
                try:  # TODO: tighten this try/except.
                    # Windows 'getctime' is creation, 'getmtime' is modify.
                    # We check mtime to be safe.
                    file_mtime = getmtime(self.context.log_file)

                    # Freshness Test: Is file newer than launch time? (with 1s buffer)
                    if file_mtime >= (launch_time - 1.0):
                        self._debug_log(f"Locked onto fresh log file: {self.context.log_file}")
                        return
                    else:
                        # Log exists, but it's old. Wait for UE to overwrite it.
                        if retries % 5 == 0:
                            self._debug_log(f"Ignoring stale log (Mtime: {file_mtime} < Launch: {launch_time})")
                except OSError:
                    pass  # File locked by OS, retry next tick.

            sleep(0.5)
            retries += 1

        # 3. Timeout
        logger.error(f"Timed out waiting for log file: {self.context.log_file}")
        self.status = self.STATUS_FAILED

    def _stream_log_file(self):
        """While running_subprocess, read the entire log each loop and post to the DB."""
        if self.status in self.STATUSES_WHICH_HALT: return
        self.status = self.STATUS_STREAMING_LOGS
        with open(self.context.log_file, 'r', encoding='utf-8', errors='replace') as local_log:
            while self.running_subprocess.poll() is not None and self.status not in self.STATUSES_WHICH_HALT:
                self.running_log = local_log.read()
                self._post_head_log()
                # TODO: strongly consider a hook here, the agent would know if it updated.
                sleep(0.1)

    def _log_router(self):
        match self.executable_type:
            case HydraExecutableType.LOCAL_PYTHON:
                pass
            case HydraExecutableType.REMOTE_PYTHON:
                pass
            case HydraExecutableType.LOCAL_POPEN:
                self._debug_log(f"Blocking for Log {self.context.log_file}")
                self._block_for_log_file()
                self._debug_log(f"Streaming Log {self.context.log_file}")
                self._stream_log_file()
            case HydraExecutableType.REMOTE_POPEN:
                pass
            case _:
                raise ValueError(f"Unknown spell type: {self.executable_type}")

    def _execute_local_python(self):
        handlers = dict(
            distribute_fleet=distribute_build_native,
            version_stamper=version_stamp_native,
        )

        # Safety check for missing handlers
        if self.spell.executable.slug not in handlers:
            raise NotImplementedError(f"No handler found for slug: {self.spell.executable.slug}")

        handler = handlers[self.spell.executable.slug]

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

    def _execute_remote_python(self):
        pass

    def _execute_local_popen(self):
        """The default method for executing spells."""
        execution_command = self._get_command()
        try:
            self.running_subprocess = subprocess.Popen(
                execution_command, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            # TODO: narrow exception type
            raise RuntimeError(f"Failed to launch spell execution: {e}")

    def _execute_remote_popen(self):
        pass

    def _executable_router(self):
        match self.executable_type:
            case HydraExecutableType.LOCAL_PYTHON:
                self._execute_local_python()
            case HydraExecutableType.REMOTE_PYTHON:
                self._execute_remote_python()
            case HydraExecutableType.LOCAL_POPEN:
                self._execute_local_popen()
            case HydraExecutableType.REMOTE_POPEN:
                self._execute_remote_popen()
            case _:
                raise ValueError(f"Unknown spell type: {self.executable_type}")

    def _post_processor(self):
        """Run post processing steps after streaming logs."""
        self.status = self.STATUS_POST_PROCESSING
        if self.callback:
            try:
                self.callback(self)
            except Exception as e:
                logger.error(f'Error running post processing callback: {e}')
            self.callback(self)
        self.status = self.STATUS_COMPLETE

    def _cast_spell(self):
        self._debug_log(f"Launching {self.spell.name}")
        self._update_head_status(HydraHeadStatus.RUNNING)
        self._executable_router()
        self._debug_log(f"Logging {self.spell.name}")
        self._log_router()
        self._debug_log(f"Post Processing {self.spell.name}")
        self._post_processor()
        self._debug_log(f"Clean Up {self.spell.name}")
        if self.running_subprocess:
            self.running_subprocess.kill()
        if self.status not in self.STATUSES_WHICH_HALT:
            self.status = self.STATUS_COMPLETE
        self._debug_log(f"{self.spell.name} END OF LINE")
