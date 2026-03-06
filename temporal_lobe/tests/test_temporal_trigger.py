import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from central_nervous_system.models import (
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from environments.models import ProjectEnvironment
from temporal_lobe.models import Iteration, IterationDefinition, IterationStatus
from temporal_lobe.temporal_lobe import (
    fetch_canonical_temporal_pathway,
    trigger_temporal_metronomes,
)


class TestTemporalMetronomeIgnition(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
        'frontal_lobe/fixtures/initial_data.json',
        'identity/fixtures/initial_data.json',
        'parietal_lobe/fixtures/initial_data.json',
        'prefrontal_cortex/fixtures/initial_data.json',
        'temporal_lobe/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Fetch the baseline records provided by the fixture
        self.env = ProjectEnvironment.objects.first()
        self.pathway = fetch_canonical_temporal_pathway()
        blueprint = IterationDefinition.objects.first()

        # Create an active Iteration to ensure the environment SHOULD be ticking
        self.iteration = Iteration.objects.create(
            name='Test Sprint 1',
            environment=self.env,
            status_id=IterationStatus.WAITING,
            definition=blueprint,
        )

    def test_clean_slate_spawns_new_metronome(self):
        """SCENARIO 1: No metronomes exist. It should spawn exactly one."""
        spawned_ids = trigger_temporal_metronomes()

        self.assertEqual(len(spawned_ids), 1)
        self.assertEqual(SpikeTrain.objects.count(), 1)
        self.assertEqual(
            SpikeTrain.objects.first().status_id, SpikeTrainStatus.RUNNING
        )

    @patch('temporal_lobe.temporal_lobe.AsyncResult')
    def test_healthy_celery_worker_skips_spawn(self, mock_async_result):
        """SCENARIO 2: Celery is actively running the metronome. Hands off."""

        # Fake an existing running train and spike
        train = SpikeTrain.objects.create(
            pathway=self.pathway,
            environment=self.env,
            status_id=SpikeTrainStatus.RUNNING,
        )
        Spike.objects.create(
            spike_train=train,
            status_id=SpikeStatus.RUNNING,
            celery_task_id=uuid.uuid4(),
        )

        # Mock Celery saying "Yep, I'm working on it!"
        mock_task = MagicMock()
        mock_task.state = 'STARTED'
        mock_async_result.return_value = mock_task

        spawned_ids = trigger_temporal_metronomes()

        # It should skip spawning entirely
        self.assertEqual(len(spawned_ids), 0)
        self.assertEqual(
            SpikeTrain.objects.count(), 1
        )  # Only the original remains

    @patch('temporal_lobe.temporal_lobe.CNS')
    @patch('temporal_lobe.temporal_lobe.AsyncResult')
    def test_ghost_worker_triggers_gc_and_respawns(
        self, mock_async_result, mock_cns
    ):
        """SCENARIO 3: DB says RUNNING, but Celery says FAILURE. It should GC and respawn."""

        # Fake a ghost train
        train = SpikeTrain.objects.create(
            pathway=self.pathway,
            environment=self.env,
            status_id=SpikeTrainStatus.RUNNING,
        )
        Spike.objects.create(
            spike_train=train,
            status_id=SpikeStatus.RUNNING,
            celery_task_id=uuid.uuid4(),
        )

        # Mock Celery saying "Task crashed/missing"
        mock_task = MagicMock()
        mock_task.state = 'FAILURE'
        mock_async_result.return_value = mock_task

        # Mock the CNS Orchestrator so we can verify it was asked to clean up
        mock_cns_instance = MagicMock()
        mock_cns.return_value = mock_cns_instance

        # To allow the respawn to pass the Bouncer, we need the mock `poll()` to simulate
        # what the real DB would do: change the train status to FAILED/STOPPED
        def fake_poll():
            train.status_id = SpikeTrainStatus.FAILED
            train.save()

        mock_cns_instance.poll.side_effect = fake_poll

        spawned_ids = trigger_temporal_metronomes()

        # 1. Did it ask the Orchestrator to clean up the ghost?
        mock_cns_instance.poll.assert_called_once()

        # 2. Did it spawn a replacement metronome?
        self.assertEqual(len(spawned_ids), 1)
        self.assertEqual(
            SpikeTrain.objects.count(), 2
        )  # The ghost (now failed) + The fresh spawn
