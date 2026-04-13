"""Logging handler that broadcasts log records as Norepinephrine via Synaptic Cleft.

Parameterized: receptor_class and skipped_prefixes are constructor kwargs so that
Django LOGGING dictConfig can instantiate multiple handlers with different routing.
The handler is re-entrance-safe via threading.Lock (not a bare boolean) because
Daphne serves concurrent async tasks on a single handler instance.
"""

import asyncio
import logging
import socket
import threading
from typing import Optional, Sequence

from asgiref.sync import async_to_sync

from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Norepinephrine

# Defaults — used when dictConfig doesn't supply overrides.
DEFAULT_RECEPTOR_CLASS = 'CeleryWorker'
DEFAULT_SKIPPED_PREFIXES = (
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
    """Broadcasts log records to the Synaptic Cleft as Norepinephrine molecules.

    Constructor kwargs (passed via Django LOGGING dictConfig):
        receptor_class: Layer 1 routing target. Defaults to 'CeleryWorker'.
        skipped_prefixes: Tuple of logger name prefixes to silently drop.
            Defaults to infrastructure loggers that would cause recursion.
    """

    def __init__(
        self,
        level: int = logging.NOTSET,
        receptor_class: Optional[str] = None,
        skipped_prefixes: Optional[Sequence[str]] = None,
    ) -> None:
        super().__init__(level)
        self._hostname = _get_worker_hostname()
        self._receptor_class = receptor_class or DEFAULT_RECEPTOR_CLASS
        self._skipped_prefixes = tuple(
            skipped_prefixes
            if skipped_prefixes is not None
            else DEFAULT_SKIPPED_PREFIXES
        )
        self._lock_fire = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record as a Norepinephrine neurotransmitter."""
        if not self._lock_fire.acquire(blocking=False):
            return

        try:
            if record.name.startswith(self._skipped_prefixes):
                return

            transmitter = Norepinephrine(
                receptor_class=self._receptor_class,
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
            self._lock_fire.release()
