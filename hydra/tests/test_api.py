import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from environments.models import TalosExecutable
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)


class HydraAPITest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Setup Auth
        self.user = User.objects.create_superuser('testadmin',
                                                  'admin@talos.dev', 'password')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # 2. Data Setup
        self.book = HydraSpellbook.objects.create(name='API Test Protocol')
        self.exe = TalosExecutable.objects.first()  # Should exist from fixtures
        if not self.exe:
            self.exe = TalosExecutable.objects.create(name='TestExe',
                                                      executable='cmd.exe')

        self.spell = HydraSpell.objects.create(name='Test Spell',
                                               talos_executable=self.exe)

        # Get statuses from fixtures
        self.status_created = HydraSpawnStatus.objects.get(id=1)
        self.head_status = HydraHeadStatus.objects.get(id=1)

    @patch('hydra.api.Hydra')
    def test_launch_spawn(self, MockHydraController):
        """
        Verify POST /api/v1/spawns/ successfully creates a spawn and triggers the engine.
        """
        # Mock the Controller instance
        mock_instance = MockHydraController.return_value

        # When the controller is initialized, we want it to simulate creating a spawn object
        # so the serializer can return it.
        mock_spawn = HydraSpawn.objects.create(spellbook=self.book,
                                               status=self.status_created)
        mock_instance.spawn = mock_spawn

        url = '/api/v1/spawns/'
        payload = {'spellbook_id': str(self.book.id)}

        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['id'], str(mock_spawn.id))

        # Verify the Engine was actually triggered
        MockHydraController.assert_called_with(spellbook_id=self.book.id)
        mock_instance.start.assert_called_once()

    def test_launch_invalid_spellbook(self):
        """Verify 400 Bad Request on missing/invalid UUID."""
        url = '/api/v1/spawns/'
        payload = {'spellbook_id': str(uuid.uuid4())}  # Random UUID

        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not found', str(response.data))

    def test_retrieve_head_telemetry(self):
        """
        Verify GET /api/v1/heads/{id}/ returns rich telemetry including reconstructed commands.
        """
        spawn = HydraSpawn.objects.create(spellbook=self.book,
                                          status=self.status_created)
        head = HydraHead.objects.create(
            spawn=spawn,
            spell=self.spell,
            status=self.head_status,
            spell_log='Output Log Content...',
            execution_log='System Context...',
        )

        url = f'/api/v1/heads/{head.id}/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify Fields from HydraNodeTelemetrySerializer
        self.assertIn('logs', response.data)
        self.assertIn('command', response.data)
        self.assertIn('delta', response.data)

        # Verify content
        self.assertIn('Output Log Content', response.data['logs'])
        # Command should contain the executable name
        self.assertIn(self.exe.executable, response.data['command'])

    def test_list_spawn_heads(self):
        """Verify the nested action /api/v1/spawns/{id}/heads/ works."""
        spawn = HydraSpawn.objects.create(spellbook=self.book,
                                          status=self.status_created)
        HydraHead.objects.create(spawn=spawn,
                                 spell=self.spell,
                                 status=self.head_status)
        HydraHead.objects.create(spawn=spawn,
                                 spell=self.spell,
                                 status=self.head_status)

        url = f'/api/v1/spawns/{spawn.id}/heads/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # Verify we are using the LIGHTWEIGHT serializer (no logs)
        self.assertNotIn('spell_log', response.data[0])
