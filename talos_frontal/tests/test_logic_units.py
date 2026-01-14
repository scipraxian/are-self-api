from unittest.mock import patch, MagicMock
from django.test import TestCase
from talos_frontal.logic import StimulusProcessor
from talos_thalamus.types import SignalTypeID
from talos_reasoning.models import ReasoningStatusID

class StimulusProcessorUnitTest(TestCase):
    def setUp(self):
        self.processor = StimulusProcessor()

    @patch('talos_frontal.logic.read_build_log')
    def test_evaluate_necessity_failed_spawn(self, mock_read):
        """Failed spawn always triggers analysis."""
        mock_read.return_value = "Log data"
        should_run, prompt = self.processor._evaluate_necessity(1, SignalTypeID.SPAWN_FAILED)
        self.assertTrue(should_run)
        self.assertIn("build failed", prompt)

    @patch('talos_frontal.logic.read_build_log')
    def test_evaluate_necessity_success_clean(self, mock_read):
        """Clean success triggers nothing."""
        mock_read.return_value = "Clean log"
        should_run, prompt = self.processor._evaluate_necessity(1, SignalTypeID.SPAWN_SUCCESS)
        self.assertFalse(should_run)

    @patch('talos_frontal.logic.read_build_log')
    def test_evaluate_necessity_success_dirty(self, mock_read):
        """Success with error strings triggers paranoid analysis."""
        mock_read.return_value = "ERROR SUMMARY: Something hidden"
        should_run, prompt = self.processor._evaluate_necessity(1, SignalTypeID.SPAWN_SUCCESS)
        self.assertTrue(should_run)
        self.assertIn("paranoid", prompt)