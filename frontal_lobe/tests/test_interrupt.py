"""Tests for interrupt polling and session INTERRUPTED status."""

from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase

from central_nervous_system.models import Spike, SpikeStatus
from frontal_lobe.frontal_lobe import spike_is_stopping


class TestSpikeIsStopping(SimpleTestCase):
    """Assert sync interrupt poll matches Spike status."""

    def test_none_spike_id_is_noop(self):
        self.assertFalse(spike_is_stopping(None))

    @patch('frontal_lobe.frontal_lobe.Spike.objects')
    def test_stopping_true(self, mock_objects):
        mock_objects.only.return_value.get.return_value.status_id = (
            SpikeStatus.STOPPING
        )
        self.assertTrue(spike_is_stopping(uuid4()))

    @patch('frontal_lobe.frontal_lobe.Spike.objects')
    def test_running_false(self, mock_objects):
        mock_objects.only.return_value.get.return_value.status_id = (
            SpikeStatus.RUNNING
        )
        self.assertFalse(spike_is_stopping(uuid4()))

    @patch('frontal_lobe.frontal_lobe.Spike.objects')
    def test_missing_spike_false(self, mock_objects):
        mock_objects.only.return_value.get.side_effect = Spike.DoesNotExist
        self.assertFalse(spike_is_stopping(uuid4()))
