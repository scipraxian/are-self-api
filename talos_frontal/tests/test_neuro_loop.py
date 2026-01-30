from unittest.mock import patch
from django.test import TestCase
from hydra.models import HydraSpawn, HydraSpellbook, HydraSpawnStatus
from talos_frontal.logic import process_stimulus
from talos_reasoning.models import ReasoningSession, ReasoningStatusID
from talos_thalamus.models import Stimulus
from talos_thalamus.types import SignalTypeID


class NeuroLoopTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.book = HydraSpellbook.objects.create(name="TestBook")
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.CREATED)

    @patch('talos_frontal.logic.read_build_log')
    @patch('talos_reasoning.engine.OllamaClient')
    def test_thought_creation_success(self, mock_engine_client, mock_read_log):
        """Integration: Signal -> Processor -> Engine -> Session"""
        mock_read_log.return_value = "ERROR SUMMARY: Broken."

        # Engine Mock: Finish immediately
        mock_engine_client.return_value.chat.side_effect = [{
            "content": "Analysis done."
        }, {
            "content": "Summary."
        }]

        stimulus = Stimulus('hydra', 'Fail', {
            'spawn_id': self.spawn.id,
            'event_type': SignalTypeID.SPAWN_FAILED
        })

        process_stimulus(stimulus)

        # Assert Session Created
        session = ReasoningSession.objects.get(spawn_link=self.spawn)
        self.assertEqual(session.status_id, ReasoningStatusID.COMPLETED)
        self.assertEqual(session.turns.count(), 1)
