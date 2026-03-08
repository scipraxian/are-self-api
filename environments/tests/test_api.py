import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
)


class EnvironmentAPITest(TestCase):
    # Load fixtures to ensure IDs and Foreign Keys are valid
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Setup Auth
        self.user = User.objects.create_superuser(
            'testadmin', 'admin@talos.dev', 'password'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # 2. Setup Logic Data
        # Get types from fixture or create if missing
        self.type_ue = ProjectEnvironmentType.objects.first()
        if not self.type_ue:
            self.type_ue = ProjectEnvironmentType.objects.create(name='UE5')

        self.status_ok = ProjectEnvironmentStatus.objects.first()
        if not self.status_ok:
            self.status_ok = ProjectEnvironmentStatus.objects.create(
                name='Ready'
            )

        self.env_dev = ProjectEnvironment.objects.create(
            name='Development_API',
            type=self.type_ue,
            status=self.status_ok,
            available=True,
            selected=True,
        )

        self.env_stage = ProjectEnvironment.objects.create(
            name='Staging_API',
            type=self.type_ue,
            status=self.status_ok,
            available=True,
            selected=False,
        )

    def test_list_environments(self):
        """Verify standard DRF list endpoint works."""
        url = '/api/v1/environments/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Fixtures + Setup = more than 2
        self.assertTrue(len(response.data) >= 2)

    def test_select_action(self):
        """Verify the custom 'select' action switches the active environment."""
        url = f'/api/v1/environments/{self.env_stage.id}/select/'

        # Verify initial state
        self.env_dev.refresh_from_db()
        self.env_stage.refresh_from_db()
        self.assertTrue(self.env_dev.selected)
        self.assertFalse(self.env_stage.selected)

        # Execute Action
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify DB Side Effects (Atomic Switch)
        self.env_dev.refresh_from_db()
        self.env_stage.refresh_from_db()

        self.assertFalse(self.env_dev.selected)
        self.assertTrue(self.env_stage.selected)

    def test_select_unavailable_environment(self):
        """Verify guardrails prevent selecting unavailable environments."""
        self.env_stage.available = False
        self.env_stage.save()

        url = f'/api/v1/environments/{self.env_stage.id}/select/'
        response = self.client.post(url)

        # API Implementation returns 409 Conflict for unavailable resources
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

        # Ensure state did NOT change
        self.env_dev.refresh_from_db()
        self.assertTrue(self.env_dev.selected)
