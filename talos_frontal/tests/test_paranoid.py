from unittest.mock import patch
from django.test import TestCase
from hydra.models import HydraSpawn, HydraSpellbook, HydraSpawnStatus
from talos_frontal.logic import process_stimulus
from talos_frontal.models import ConsciousStream, ConsciousStatusID
from talos_thalamus.models import Stimulus
from talos_thalamus.types import SignalTypeID
from talos_reasoning.models import ReasoningSession, ReasoningStatusID


class ParanoidLogicTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
        'talos_frontal/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.book = HydraSpellbook.objects.create(name="TestBook")
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.CREATED)

    @patch('talos_frontal.logic.read_build_log')
    @patch('talos_frontal.logic.ReasoningEngine')
    def test_spawn_failed_triggers_analysis(self, mock_engine_cls,
                                            mock_read_log):
        """Scenario 1: Spawn Failed -> Session Created & Engine Ticked."""
        mock_read_log.return_value = "ERROR SUMMARY: Failure"

        # FIX: The mock engine must actually COMPLETE the work, or the loop spins forever.
        def mock_tick(session_id):
            s = ReasoningSession.objects.get(id=session_id)
            s.status_id = ReasoningStatusID.COMPLETED
            s.save()

        mock_engine_cls.return_value.tick.side_effect = mock_tick

        process_stimulus(
            Stimulus('hydra', 'Fail', {
                'spawn_id': self.spawn.id,
                'event_type': SignalTypeID.SPAWN_FAILED
            }))

        session = ReasoningSession.objects.get(spawn_link=self.spawn)
        self.assertIn("failed", session.goals.first().reasoning_prompt)

        mock_engine_cls.return_value.tick.assert_called()

    @patch('talos_frontal.logic.read_build_log')
    @patch('talos_frontal.logic.ReasoningEngine')
    def test_spawn_success_with_errors_triggers_analysis(
            self, mock_engine_cls, mock_read_log):
        """Scenario 2: Success + Errors -> Session Created."""
        mock_read_log.return_value = "ERROR SUMMARY: Hidden Error"

        def mock_tick(session_id):
            s = ReasoningSession.objects.get(id=session_id)
            s.status_id = ReasoningStatusID.COMPLETED
            s.save()

        mock_engine_cls.return_value.tick.side_effect = mock_tick

        process_stimulus(
            Stimulus('hydra', 'Success', {
                'spawn_id': self.spawn.id,
                'event_type': SignalTypeID.SPAWN_SUCCESS
            }))

        session = ReasoningSession.objects.get(spawn_link=self.spawn)
        # FIX: Matches logic.py casing "paranoid analysis"
        self.assertIn("paranoid analysis",
                      session.goals.first().reasoning_prompt)

    @patch('talos_frontal.logic.read_build_log')
    def test_spawn_success_clean_log(self, mock_read_log):
        """Scenario 3: Success + Clean -> No Session."""
        mock_read_log.return_value = "Clean log"

        process_stimulus(
            Stimulus('hydra', 'Success', {
                'spawn_id': self.spawn.id,
                'event_type': SignalTypeID.SPAWN_SUCCESS
            }))

        self.assertFalse(
            ReasoningSession.objects.filter(spawn_link=self.spawn).exists())
