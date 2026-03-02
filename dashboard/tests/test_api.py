from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
)
from central_nervous_system.models import NeuralPathway


class DashboardAPITest(TestCase):
    # CRITICAL: Order matters. Environments -> Agent Statuses -> Agents -> CNS
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Setup Auth
        self.user = User.objects.create_superuser(
            'testadmin', 'admin@talos.dev', 'password'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_summary_endpoint(self):
        """Verify the summary endpoint aggregates the required UI data."""
        type_ue = ProjectEnvironmentType.objects.first()
        status_ok = ProjectEnvironmentStatus.objects.first()

        ProjectEnvironment.objects.create(
            name='Test Env API', type=type_ue, status=status_ok
        )
        NeuralPathway.objects.create(name='Test Protocol API')

        url = '/api/v1/dashboard/summary/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('environments', response.data)
        self.assertIn('pathways', response.data)
        self.assertIn('recent_missions', response.data)
        self.assertTrue(len(response.data['environments']) > 0)
        self.assertTrue(len(response.data['pathways']) > 0)

    @patch('dashboard.api.threading.Thread.start')
    @patch('dashboard.api.celery_app.control.shutdown')
    def test_shutdown_endpoint(self, mock_celery_shutdown, mock_thread_start):
        """Verify shutdown triggers Celery control and schedules a shutdown thread."""
        url = '/api/v1/dashboard/shutdown/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the backend actions were triggered
        mock_celery_shutdown.assert_called_once()
        mock_thread_start.assert_called_once()
