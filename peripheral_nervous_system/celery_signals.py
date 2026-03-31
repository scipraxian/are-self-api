"""Celery in-process signal handlers that broadcast worker activity as Norepinephrine."""

import logging
import socket
from typing import Optional

from asgiref.sync import async_to_sync
from celery.signals import (
    heartbeat_sent,
    task_failure,
    task_postrun,
    task_prerun,
    worker_ready,
    worker_shutting_down,
)

from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Norepinephrine

logger = logging.getLogger(__name__)

RECEPTOR_CLASS = 'CeleryWorker'


def _get_hostname() -> str:
    """Return the Celery worker hostname or fall back to socket hostname."""
    try:
        from celery import current_app
        hostname = (
            current_app.current_worker_task
            and current_app.current_worker_task.request.hostname
        )
        if hostname:
            return hostname
    except Exception:
        pass
    return f'celery@{socket.gethostname()}'


def _fire(
    activity: str, hostname: str, vesicle: Optional[dict] = None
) -> None:
    """Build and fire a Norepinephrine neurotransmitter."""
    transmitter = Norepinephrine(
        receptor_class=RECEPTOR_CLASS,
        dendrite_id=hostname,
        activity=activity,
        vesicle=vesicle or {},
    )
    try:
        async_to_sync(fire_neurotransmitter)(transmitter)
    except Exception as e:
        logger.debug('[PNS] Failed to fire Norepinephrine: %s', e)


@worker_ready.connect
def on_worker_ready(sender: object, **kwargs: object) -> None:
    """Handle worker_ready signal."""
    hostname = str(sender) if sender else _get_hostname()
    logger.info('[PNS] Worker online: %s', hostname)
    _fire('worker_online', hostname, {'hostname': hostname})


@worker_shutting_down.connect
def on_worker_shutdown(
    sig: object, how: object, exitcode: object, **kwargs: object
) -> None:
    """Handle worker_shutting_down signal."""
    hostname = _get_hostname()
    logger.info('[PNS] Worker shutting down: %s', hostname)
    _fire('worker_offline', hostname, {'hostname': hostname})


@task_prerun.connect
def on_task_prerun(
    sender: object,
    task_id: str,
    task: object,
    args: tuple,
    kwargs: dict,
    **kw: object
) -> None:
    """Handle task_prerun signal."""
    hostname = _get_hostname()
    _fire('task_started', hostname, {
        'uuid': str(task_id),
        'name': task.name if hasattr(task, 'name') else str(task),
        'hostname': hostname,
    })


@task_postrun.connect
def on_task_postrun(
    sender: object,
    task_id: str,
    task: object,
    args: tuple,
    kwargs: dict,
    retval: object,
    state: str,
    **kw: object
) -> None:
    """Handle task_postrun signal."""
    hostname = _get_hostname()
    activity = 'task_succeeded' if state == 'SUCCESS' else 'task_failed'
    vesicle = {
        'uuid': str(task_id),
        'name': task.name if hasattr(task, 'name') else str(task),
        'hostname': hostname,
        'state': state,
    }
    if state != 'SUCCESS' and retval:
        vesicle['exception'] = str(retval)
    _fire(activity, hostname, vesicle)


@task_failure.connect
def on_task_failure(
    sender: object,
    task_id: str,
    exception: Exception,
    traceback: object,
    **kwargs: object
) -> None:
    """Handle task_failure signal."""
    hostname = _get_hostname()
    _fire('task_failed', hostname, {
        'uuid': str(task_id),
        'name': (
            sender.name if hasattr(sender, 'name') else str(sender)
        ),
        'hostname': hostname,
        'exception': str(exception),
    })


@heartbeat_sent.connect
def on_heartbeat(sender: object, **kwargs: object) -> None:
    """Handle heartbeat_sent signal."""
    hostname = _get_hostname()
    _fire('heartbeat', hostname, {'hostname': hostname})
