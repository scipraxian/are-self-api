# dashboard/tests/test_dashboard_views.py
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
        # FIX: Added 'dashboard:' namespace
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/mission_control.html')
        self.assertContains(response, 'TALOS ORCHESTRATOR')

    def test_shutdown_button_exists_in_frontend(self):
        """Verifies the shutdown button is wired to the correct API endpoint via HTMX."""
        # Note: Using reverse('dashboard:home') to fetch the main dashboard view
        response = self.client.get(reverse('dashboard:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'hx-post="/api/v1/dashboard/shutdown/"',
            msg_prefix='Shutdown HTMX post target missing from the System Menu.',
        )


class DashboardTaskTests(TestCase):
    """Tests for the dashboard tasks."""

    def test_debug_task_execution(self):
        """Test the Celery task directly."""
        result = debug_task.apply()
        self.assertEqual(result.result, 'Task Finished')
        self.assertTrue(result.successful())


class DashboardBrokerTests(TestCase):
    """Verifies connection to the message broker. (Integration tests, require LIVE Redis)."""

    @pytest.mark.live
    def test_broker_connection(self):
        """Verifies that Celery can connect to the configured broker (Integration w/ Redis)."""
        try:
            with celery_app.connection() as connection:
                connection.connect()
                self.assertTrue(connection.connected)
        except Exception as e:
            self.fail(f'Celery could not connect to the broker: {e}')
