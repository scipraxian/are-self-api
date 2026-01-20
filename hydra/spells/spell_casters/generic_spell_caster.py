import logging
import subprocess
import uuid
from os.path import exists
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


class GenericSpellTypes(object):
    LOCAL_PYTHON = 1
    REMOTE_PYTHON = 2
    LOCAL_POPEN = 3
    REMOTE_POPEN = 4



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

    def __init__(self, head_id: uuid, context: SpellContext, callback = None): # todo: strongly type callback
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
        env = self.head.spawn.environment.project_environment

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

    def _preflight(self):
        self._debug_log(f"Preflight for {self.spell.name}")
        self._generate_context()
        self._init_running_log()
        self._resolve_switches()
        if not exists(self.context.executable):
            raise FileNotFoundError(f"Could not find executable at {self.context.executable}")
        if not exists(self.context.log_file):
            raise FileNotFoundError(f"Could not find log file at {self.context.log_file}")

    def _get_command(self):
        return f'{self.context.executable} {self.switch_string}'

    def _block_for_log(self):
        """Block until the log file is created."""
        stop_counter = 0
        while not exists(self.context.log_file):
            sleep(0.1)
            stop_counter += 1
            if stop_counter > 100:
                raise TimeoutError(f"Log file creation timed out after {stop_counter} attempts")

    def _post_log(self):
        """Save the log to the DB. TODO: do this asynchronously, it may block."""
        self._debug_log(f"Post Log {self.context.log_file}")
        self.head.spell_log = "".join(self.running_log)

    def _stream_log(self):
        """While running_subprocess, read the entire log each loop and post to the DB."""
        self.status = self.STATUS_STREAMING_LOGS
        with open(self.context.log_file, 'r', encoding='utf-8', errors='replace') as local_log:
            while self.running_subprocess.poll() is not None and self.status not in self.STATUSES_WHICH_HALT:
                self.running_log = local_log.read()
                self._post_log()
                # TODO: strongly consider a hook here, the agent would know if it updated.
                sleep(0.1)

    def _execute_local_python(self):
        handlers = dict(
            distribute_fleet=distribute_build_native,
            version_stamper=version_stamp_native,
        )
        handler = handlers[self.spell.executable.slug]

        # TODO: consider an async option here (no return).
        output_log = 'attempting'
        return_code = 1
        try:
            return_code, output_log = handler(self.head_id)
        except Exception as e:
            self.head.spell_log = f'Native Handler Exception: {str(e)}'
            self.head.status_id = HydraHeadStatus.FAILED
            self.head.save()
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
        if self.executable_type == HydraExecutableType.LOCAL_PYTHON:
            self._execute_local_python()
        elif self.executable_type == HydraExecutableType.REMOTE_PYTHON:
            self._execute_remote_python()
        elif self.executable_type == HydraExecutableType.LOCAL_POPEN:
            self._execute_local_popen()
        elif self.executable_type == HydraExecutableType.REMOTE_POPEN:
            self._execute_remote_popen()
        else:
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
        self._debug_log(f"Blocking for Log {self.context.log_file}")
        self._block_for_log()
        self._debug_log(f"Streaming Log {self.context.log_file}")
        self._stream_log()
        self._debug_log(f"Post Processing {self.spell.name}")
        self._post_processor()
        self.status = self.STATUS_COMPLETE


