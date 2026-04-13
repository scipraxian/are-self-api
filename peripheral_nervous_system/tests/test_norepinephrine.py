"""Tests for Norepinephrine neurotransmitter and related infrastructure."""

import logging
from unittest.mock import MagicMock, patch

from rest_framework import status

from common.tests.common_test_case import CommonTestCase
from peripheral_nervous_system.celery_signals import (
    on_task_postrun,
    on_task_prerun,
    on_worker_ready,
)
from synaptic_cleft.neurotransmitters import Norepinephrine
from synaptic_cleft.norepinephrine_handler import NorepinephrineHandler


class NorepinephrineModelTests(CommonTestCase):
    """Tests for the Norepinephrine neurotransmitter class."""

    def test_norepinephrine_auto_labels_molecule(self):
        """Assert Norepinephrine auto-sets molecule to 'Norepinephrine'."""
        norepi = Norepinephrine(
            receptor_class='CeleryWorker',
            dendrite_id='celery@localhost',
            activity='heartbeat',
            vesicle={'active': 3, 'loadavg': [0.5, 0.3, 0.2]},
        )
        assert norepi.molecule == 'Norepinephrine'

    def test_norepinephrine_synapse_dict_format(self):
        """Assert to_synapse_dict produces valid Channels message."""
        norepi = Norepinephrine(
            receptor_class='CeleryWorker',
            dendrite_id='celery@WORKSTATION',
            activity='task_started',
            vesicle={'uuid': 'abc-123', 'name': 'cast_cns_spell'},
        )
        msg = norepi.to_synapse_dict()
        assert msg['type'] == 'release_neurotransmitter'
        payload = msg['payload']
        assert payload['receptor_class'] == 'CeleryWorker'
        assert payload['dendrite_id'] == 'celery@WORKSTATION'
        assert payload['molecule'] == 'Norepinephrine'
        assert payload['activity'] == 'task_started'
        assert payload['vesicle']['name'] == 'cast_cns_spell'

    def test_norepinephrine_default_activity(self):
        """Assert Norepinephrine defaults activity to 'event'."""
        norepi = Norepinephrine(
            receptor_class='CeleryWorker',
            dendrite_id='celery@localhost',
            vesicle={},
        )
        assert norepi.activity == 'event'


class NorepinephrineHandlerTests(CommonTestCase):
    """Tests for the NorepinephrineHandler logging handler."""

    def test_handler_reentrancy_guard(self):
        """Assert handler drops the record when the lock is already held."""
        handler = NorepinephrineHandler()
        # Simulate "a broadcast is already in flight" by holding the lock.
        handler._lock_fire.acquire()
        try:
            with patch(
                'synaptic_cleft.norepinephrine_handler.fire_neurotransmitter'
            ) as mock_fire:
                record = logging.LogRecord(
                    name='central_nervous_system',
                    level=logging.INFO,
                    pathname='',
                    lineno=0,
                    msg='Should be dropped',
                    args=(),
                    exc_info=None,
                )
                handler.emit(record)
                mock_fire.assert_not_called()
        finally:
            handler._lock_fire.release()

    def test_handler_skips_infrastructure_loggers(self):
        """Assert handler ignores synaptic_cleft, channels, daphne, redis, asyncio loggers."""
        handler = NorepinephrineHandler()
        infrastructure_loggers = [
            'synaptic_cleft.axon_hillok',
            'channels.layers',
            'daphne.server',
            'redis.connection',
            'asyncio',
        ]
        with patch(
            'synaptic_cleft.norepinephrine_handler.fire_neurotransmitter'
        ) as mock_fire:
            for logger_name in infrastructure_loggers:
                record = logging.LogRecord(
                    name=logger_name,
                    level=logging.INFO,
                    pathname='',
                    lineno=0,
                    msg='Infrastructure log',
                    args=(),
                    exc_info=None,
                )
                handler.emit(record)
            mock_fire.assert_not_called()

    @patch(
        'synaptic_cleft.norepinephrine_handler.async_to_sync'
    )
    def test_handler_fires_norepinephrine(self, mock_async_to_sync):
        """Assert handler creates and fires Norepinephrine for valid log records."""
        mock_fire = MagicMock()
        mock_async_to_sync.return_value = mock_fire

        handler = NorepinephrineHandler()
        handler.setFormatter(
            logging.Formatter('[%(levelname)s] %(message)s')
        )
        record = logging.LogRecord(
            name='central_nervous_system',
            level=logging.INFO,
            pathname='cns.py',
            lineno=42,
            msg='Spike %s started',
            args=('abc-123',),
            exc_info=None,
        )
        handler.emit(record)

        mock_fire.assert_called_once()
        transmitter = mock_fire.call_args[0][0]
        assert isinstance(transmitter, Norepinephrine)
        assert transmitter.activity == 'log'
        assert transmitter.receptor_class == 'CeleryWorker'
        assert transmitter.vesicle['logger'] == 'central_nervous_system'
        assert transmitter.vesicle['level'] == 'INFO'
        assert 'Spike abc-123 started' in transmitter.vesicle['message']
        assert transmitter.vesicle['lineno'] == 42


    @patch(
        'synaptic_cleft.norepinephrine_handler.async_to_sync'
    )
    def test_handler_uses_custom_receptor_class(self, mock_async_to_sync):
        """Assert receptor_class kwarg overrides the default CeleryWorker."""
        mock_fire = MagicMock()
        mock_async_to_sync.return_value = mock_fire

        handler = NorepinephrineHandler(receptor_class='Django')
        handler.setFormatter(
            logging.Formatter('[%(levelname)s] %(message)s')
        )
        record = logging.LogRecord(
            name='django.request',
            level=logging.WARNING,
            pathname='base.py',
            lineno=10,
            msg='Not Found: /missing',
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        mock_fire.assert_called_once()
        transmitter = mock_fire.call_args[0][0]
        self.assertEqual(transmitter.receptor_class, 'Django')

    def test_handler_uses_custom_skipped_prefixes(self):
        """Assert skipped_prefixes kwarg overrides the default skip list.

        A handler with a custom skip list that omits 'daphne' should
        let daphne records through. The default handler blocks them.
        """
        custom_handler = NorepinephrineHandler(
            skipped_prefixes=['synaptic_cleft', 'channels'],
        )
        default_handler = NorepinephrineHandler()

        record = logging.LogRecord(
            name='daphne.server',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg='Daphne lifecycle event',
            args=(),
            exc_info=None,
        )

        with patch(
            'synaptic_cleft.norepinephrine_handler.fire_neurotransmitter'
        ) as mock_fire:
            # Default handler should skip daphne.
            default_handler.emit(record)
            mock_fire.assert_not_called()

        with patch(
            'synaptic_cleft.norepinephrine_handler.async_to_sync'
        ) as mock_async_to_sync:
            mock_fire = MagicMock()
            mock_async_to_sync.return_value = mock_fire
            # Custom handler should let daphne through.
            custom_handler.emit(record)
            mock_fire.assert_called_once()


class CeleryWorkerAPITests(CommonTestCase):
    """Tests for the Celery worker list API endpoint."""

    @patch(
        'peripheral_nervous_system.autonomic_nervous_system.celery_app'
    )
    def test_celery_workers_endpoint(self, mock_celery_app):
        """Assert GET /api/v2/celery-workers/ returns worker list."""
        mock_inspect = MagicMock()
        mock_celery_app.control.inspect.return_value = mock_inspect
        mock_inspect.active.return_value = {
            'celery@worker1': [
                {'id': 'task-1', 'name': 'cast_cns_spell'},
            ],
        }
        mock_inspect.stats.return_value = {
            'celery@worker1': {
                'pool': {'max-concurrency': 4},
                'pid': 12345,
                'prefetch_count': 4,
            },
        }
        mock_inspect.reserved.return_value = {
            'celery@worker1': [],
        }

        response = self.test_client.get('/api/v2/celery-workers/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'workers' in data
        assert len(data['workers']) == 1
        worker = data['workers'][0]
        assert worker['hostname'] == 'celery@worker1'
        assert len(worker['active_tasks']) == 1
        assert worker['pid'] == 12345

    @patch(
        'peripheral_nervous_system.autonomic_nervous_system.celery_app'
    )
    def test_celery_workers_unreachable(self, mock_celery_app):
        """Assert GET /api/v2/celery-workers/ returns 503 when workers unreachable."""
        mock_inspect = MagicMock()
        mock_celery_app.control.inspect.return_value = mock_inspect
        mock_inspect.active.side_effect = Exception('Connection refused')

        response = self.test_client.get('/api/v2/celery-workers/')
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


class TestCelerySignals(CommonTestCase):
    """Tests for Celery in-process signal handlers."""

    @patch('peripheral_nervous_system.celery_signals._fire')
    def test_worker_ready_fires_norepinephrine(self, mock_fire):
        """Assert worker_ready signal fires worker_online Norepinephrine."""
        on_worker_ready(sender='celery@TESTHOST')
        mock_fire.assert_called_once()
        args = mock_fire.call_args
        assert args[0][0] == 'worker_online'
        assert args[0][1] == 'celery@TESTHOST'

    @patch('peripheral_nervous_system.celery_signals._fire')
    def test_task_prerun_fires_norepinephrine(self, mock_fire):
        """Assert task_prerun signal fires task_started Norepinephrine."""
        mock_task = MagicMock()
        mock_task.name = 'central_nervous_system.tasks.run_session'
        on_task_prerun(
            sender=mock_task,
            task_id='abc-123',
            task=mock_task,
            args=[],
            kwargs={},
        )
        mock_fire.assert_called_once()
        args = mock_fire.call_args
        assert args[0][0] == 'task_started'
        assert args[0][2]['name'] == (
            'central_nervous_system.tasks.run_session'
        )

    @patch('peripheral_nervous_system.celery_signals._fire')
    def test_task_postrun_success(self, mock_fire):
        """Assert task_postrun with SUCCESS state fires task_succeeded."""
        mock_task = MagicMock()
        mock_task.name = 'run_session'
        on_task_postrun(
            sender=mock_task,
            task_id='abc-123',
            task=mock_task,
            args=[],
            kwargs={},
            retval=None,
            state='SUCCESS',
        )
        args = mock_fire.call_args
        assert args[0][0] == 'task_succeeded'

    @patch('peripheral_nervous_system.celery_signals._fire')
    def test_task_postrun_failure(self, mock_fire):
        """Assert task_postrun with FAILURE state fires task_failed."""
        mock_task = MagicMock()
        mock_task.name = 'run_session'
        on_task_postrun(
            sender=mock_task,
            task_id='abc-123',
            task=mock_task,
            args=[],
            kwargs={},
            retval=Exception('boom'),
            state='FAILURE',
        )
        args = mock_fire.call_args
        assert args[0][0] == 'task_failed'
        assert args[0][2]['exception'] == 'boom'
