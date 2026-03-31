"""Management command to monitor Celery worker events and broadcast via Synaptic Cleft."""

import logging
import time

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand

from config.celery import app as celery_app
from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Norepinephrine

logger = logging.getLogger(__name__)

RECEPTOR_CLASS = 'CeleryWorker'

RETRY_DELAY_SECONDS = 5

WORKER_ONLINE = 'worker_online'
WORKER_OFFLINE = 'worker_offline'
HEARTBEAT = 'heartbeat'
TASK_RECEIVED = 'task_received'
TASK_STARTED = 'task_started'
TASK_SUCCEEDED = 'task_succeeded'
TASK_FAILED = 'task_failed'


def _fire(activity: str, hostname: str, vesicle: dict) -> None:
    """Build and fire a Norepinephrine neurotransmitter."""
    transmitter = Norepinephrine(
        receptor_class=RECEPTOR_CLASS,
        dendrite_id=hostname,
        activity=activity,
        vesicle=vesicle,
    )
    async_to_sync(fire_neurotransmitter)(transmitter)


def _safe_get(event: dict, *keys: str) -> dict:
    """Extract only the specified keys from an event dict."""
    return {k: event.get(k) for k in keys}


class Command(BaseCommand):
    """Monitor Celery worker events and broadcast via Synaptic Cleft."""

    help = 'Monitor Celery worker events and broadcast via Synaptic Cleft.'

    def handle(self, *args: str, **options: str) -> None:
        """Connect to Celery event stream and relay events as Norepinephrine."""
        logger.info('[PNS] Starting Celery event monitor...')

        logger.info('[PNS] Enabling Celery events on all workers...')
        celery_app.control.enable_events()

        state = celery_app.events.State()

        def on_worker_online(event: dict) -> None:
            state.event(event)
            hostname = event.get('hostname', '')
            logger.info('[PNS] Worker online: %s', hostname)
            _fire(
                WORKER_ONLINE,
                hostname,
                _safe_get(
                    event, 'hostname', 'sw_ident', 'sw_ver', 'sw_sys'
                ),
            )

        def on_worker_offline(event: dict) -> None:
            state.event(event)
            hostname = event.get('hostname', '')
            logger.info('[PNS] Worker offline: %s', hostname)
            _fire(WORKER_OFFLINE, hostname, _safe_get(event, 'hostname'))

        def on_worker_heartbeat(event: dict) -> None:
            state.event(event)
            hostname = event.get('hostname', '')
            _fire(
                HEARTBEAT,
                hostname,
                _safe_get(
                    event,
                    'hostname',
                    'active',
                    'loadavg',
                    'freq',
                    'sw_ident',
                    'sw_ver',
                    'clock',
                ),
            )

        def on_task_received(event: dict) -> None:
            state.event(event)
            hostname = event.get('hostname', '')
            logger.info(
                '[PNS] Task received: %s on %s',
                event.get('name'),
                hostname,
            )
            _fire(
                TASK_RECEIVED,
                hostname,
                _safe_get(
                    event, 'uuid', 'name', 'args', 'kwargs', 'hostname'
                ),
            )

        def on_task_started(event: dict) -> None:
            state.event(event)
            hostname = event.get('hostname', '')
            logger.info(
                '[PNS] Task started: %s on %s',
                event.get('name'),
                hostname,
            )
            _fire(
                TASK_STARTED,
                hostname,
                _safe_get(event, 'uuid', 'name', 'hostname', 'pid'),
            )

        def on_task_succeeded(event: dict) -> None:
            state.event(event)
            hostname = event.get('hostname', '')
            logger.info(
                '[PNS] Task succeeded: %s on %s',
                event.get('name'),
                hostname,
            )
            _fire(
                TASK_SUCCEEDED,
                hostname,
                _safe_get(
                    event, 'uuid', 'name', 'hostname', 'runtime', 'result'
                ),
            )

        def on_task_failed(event: dict) -> None:
            state.event(event)
            hostname = event.get('hostname', '')
            logger.warning(
                '[PNS] Task failed: %s on %s',
                event.get('name'),
                hostname,
            )
            _fire(
                TASK_FAILED,
                hostname,
                _safe_get(
                    event,
                    'uuid',
                    'name',
                    'hostname',
                    'exception',
                    'traceback',
                ),
            )

        handlers = {
            'worker-online': on_worker_online,
            'worker-offline': on_worker_offline,
            'worker-heartbeat': on_worker_heartbeat,
            'task-received': on_task_received,
            'task-started': on_task_started,
            'task-succeeded': on_task_succeeded,
            'task-failed': on_task_failed,
        }

        while True:
            try:
                logger.info(
                    '[PNS] Connecting to Celery broker at %s...',
                    celery_app.conf.broker_url,
                )
                with celery_app.connection() as connection:
                    recv = celery_app.events.Receiver(
                        connection, handlers=handlers
                    )
                    logger.info(
                        '[PNS] Connected. Capturing Celery events...'
                    )
                    recv.capture(
                        limit=None, timeout=None, wakeup=True
                    )
            except KeyboardInterrupt:
                logger.info('[PNS] Event monitor stopped by user.')
                break
            except Exception:
                logger.exception(
                    '[PNS] Lost connection to broker. '
                    'Retrying in %d seconds...',
                    RETRY_DELAY_SECONDS,
                )
                time.sleep(RETRY_DELAY_SECONDS)
