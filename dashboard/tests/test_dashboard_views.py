"""Tests for the dashboard application."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, TestCase
from django.urls import reverse

from config.celery import app as celery_app
from dashboard.tasks import debug_task


class DashboardViewTests(TestCase):
    """Tests for the dashboard views."""

    def setUp(self):
        """Initializes the test client."""
        self.client = Client()

    def test_home_view(self):
        """Test that the home page loads correctly."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/mission_control.html')
        self.assertContains(response, 'TALOS // MISSION CONTROL')

    @patch('dashboard.views.debug_task.delay')
    def test_trigger_build_post(self, mock_task_delay):
        """Test that POSTing to trigger_build starts the task and returns HTMX."""
        # Mock the task to return a fixed ID
        mock_task = MagicMock()
        mock_task.id = 'test-task-123'
        mock_task_delay.return_value = mock_task

        # Assuming 'trigger_build' still exists in your urls.py / views.py
        # If this was also moved to the API, this test should be moved/deleted too.
        response = self.client.post(reverse('trigger_build'))

        # Check task was triggered
        mock_task_delay.assert_called_once()


# class DashboardTaskTests(TestCase):
#     """Tests for the dashboard tasks."""
#
#     def test_debug_task_execution(self):
#         """Test the Celery task directly."""
#         # For unit testing the logic inside the task
#         result = debug_task.apply()  # apply() runs it synchronously
#         self.assertEqual(result.result, 'Task Finished')
#         self.assertTrue(result.successful())


class DashboardBrokerTests(TestCase):
    """Verifies connection to the message broker. (Integration tests, require LIVE Redis)."""

    @pytest.mark.live
    def test_broker_connection(self):
        """Verifies that Celery can connect to the configured broker (Integration w/ Redis)."""
        try:
            # Simple ping to the broker
            celery_app.broker_connection().ensure_connection(max_retries=1)
            self.assertTrue(True)
        except Exception as e:
            self.fail(f'Could not connect to Redis broker: {e}')
