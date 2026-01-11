from django.test import TestCase
from unittest.mock import patch, MagicMock
from talos_frontal.models import ConsciousStream, ConsciousStatus, ConsciousStatusID
from talos_thalamus.models import Stimulus
from talos_thalamus.types import SignalTypeID
from talos_frontal.logic import process_stimulus
from hydra.models import HydraSpawn, HydraSpellbook, HydraEnvironment, HydraSpawnStatus
from environments.models import ProjectEnvironment


class NeuroLoopTest(TestCase):

    def setUp(self):
        # Create Conscious Statuses
        if not ConsciousStatus.objects.filter(
                id=ConsciousStatusID.THINKING).exists():
            ConsciousStatus.objects.create(id=ConsciousStatusID.THINKING,
                                           name='Thinking')
            ConsciousStatus.objects.create(id=ConsciousStatusID.WAITING,
                                           name='Waiting')
            ConsciousStatus.objects.create(id=ConsciousStatusID.DONE,
                                           name='Done')

        # Populate Hydra Statuses
        if not HydraSpawnStatus.objects.filter(
                id=HydraSpawnStatus.CREATED).exists():
            HydraSpawnStatus.objects.create(id=HydraSpawnStatus.CREATED,
                                            name='Created')
            HydraSpawnStatus.objects.create(id=HydraSpawnStatus.PENDING,
                                            name='Pending')
            HydraSpawnStatus.objects.create(id=HydraSpawnStatus.RUNNING,
                                            name='Running')
            HydraSpawnStatus.objects.create(id=HydraSpawnStatus.SUCCESS,
                                            name='Success')
            HydraSpawnStatus.objects.create(id=HydraSpawnStatus.FAILED,
                                            name='Failed')

        self.pe = ProjectEnvironment.objects.create(name="TestEnv",
                                                    project_root="C:/Test")
        self.he = HydraEnvironment.objects.create(project_environment=self.pe)
        self.book = HydraSpellbook.objects.create(name="TestBook")
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            environment=self.he,
            status_id=HydraSpawnStatus.CREATED)

    @patch('talos_frontal.logic.read_build_log')
    @patch('talos_frontal.logic.OllamaClient')
    def test_thought_creation_success(self, mock_ollama_cls, mock_read_log):
        # Setup Mocks
        mock_read_log.return_value = "Error: Something broke."
        mock_client = mock_ollama_cls.return_value
        mock_client.chat.return_value = "Fix it by turning it off and on again."

        # Stimulate
        stimulus = Stimulus(source='hydra',
                            description="Spawn Failed",
                            context_data={
                                'spawn_id': self.spawn.id,
                                'event_type': SignalTypeID.SPAWN_FAILED
                            })

        process_stimulus(stimulus)

        # Assertions
        stream = ConsciousStream.objects.get(spawn_link=self.spawn)
        self.assertEqual(stream.status_id, ConsciousStatusID.DONE)
        self.assertIn("Fix it", stream.current_thought)

    def test_thought_creation_no_log(self):
        with patch('talos_frontal.logic.read_build_log', return_value=""):
            stimulus = Stimulus(source='hydra',
                                description="Spawn Failed",
                                context_data={
                                    'spawn_id': self.spawn.id,
                                    'event_type': SignalTypeID.SPAWN_FAILED
                                })
            process_stimulus(stimulus)

            stream = ConsciousStream.objects.get(spawn_link=self.spawn)
            self.assertEqual(stream.status_id, ConsciousStatusID.DONE)
            self.assertIn("No log data", stream.current_thought)
