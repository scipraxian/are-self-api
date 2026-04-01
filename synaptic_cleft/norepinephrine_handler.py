"""Logging handler that broadcasts log records as Norepinephrine via Synaptic Cleft."""

import asyncio
import logging
import socket

from asgiref.sync import async_to_sync

from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Norepinephrine

RECEPTOR_CLASS = 'CeleryWorker'

SKIPPED_LOGGER_PREFIXES = (
    'synaptic_cleft',
    'channels',
    'daphne',
    'redis',
    'asyncio',
    'peripheral_nervous_system',
)


def _get_worker_hostname() -> str:
    """Return the Celery worker hostname if available, else socket hostname."""
    try:
        from celery import current_app

        worker_hostname = current_app.current_worker_task
        if worker_hostname and hasattr(worker_hostname, 'request'):
            hostname = worker_hostname.request.hostname
            if hostname:
                return hostname
    except Exception:
        pass
    return socket.gethostname()


class NorepinephrineHandler(logging.Handler):
    """Broadcasts log records to the Synaptic Cleft as Norepinephrine molecules."""

    def __init__(self, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self._hostname = _get_worker_hostname()
        self._firing = False

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record as a Norepinephrine neurotransmitter."""
        if self._firing:
            return

        if record.name.startswith(SKIPPED_LOGGER_PREFIXES):
            return

        self._firing = True
        try:
            transmitter = Norepinephrine(
                receptor_class=RECEPTOR_CLASS,
                dendrite_id=self._hostname,
                activity='log',
                vesicle={
                    'logger': record.name,
                    'level': record.levelname,
                    'message': self.format(record),
                    'funcName': record.funcName,
                    'lineno': record.lineno,
                },
            )
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                loop.create_task(fire_neurotransmitter(transmitter))
            else:
                async_to_sync(fire_neurotransmitter)(transmitter)
        except Exception:
            self.handleError(record)
        finally:
            self._firing = False
