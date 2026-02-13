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
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/mission_control.html')
        self.assertContains(response, 'TALOS // MISSION CONTROL')


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
