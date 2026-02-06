from django.test import Client, TestCase
from django.urls import reverse

from environments.models import TalosExecutable
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)


class StopLogicTests(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        self.client = Client()

        # Get statuses (Running=3, Stopping=8)
        self.status_running = HydraSpawnStatus.objects.get(id=3)
        self.head_running = HydraHeadStatus.objects.get(id=3)

        # Create minimal graph
        self.book = HydraSpellbook.objects.create(name='Stop Test Protocol')
        self.exe = TalosExecutable.objects.first()
        if not self.exe:
            self.exe = TalosExecutable.objects.create(
                name='TestExe', executable='echo'
            )

        self.spell = HydraSpell.objects.create(
            name='Test Spell', talos_executable=self.exe
        )

        # Create Active Spawn
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status=self.status_running
        )

        self.head = HydraHead.objects.create(
            spawn=self.spawn, spell=self.spell, status=self.head_running
        )

    def test_stop_gracefully_updates_db(self):
        """
        Verify that the view triggers the DB update that the Agent watches for.
        """
        url = (
            reverse(
                'hydra:hydra_spawn_stop_graceful', kwargs={'pk': self.spawn.id}
            )
            + '?silent=true'
        )

        # Simulate button click
        response = self.client.post(url, HTTP_HX_REQUEST='true')

        # Expect 204 No Content (Silent success)
        self.assertEqual(response.status_code, 204)

        # Verify DB Updates
        self.spawn.refresh_from_db()
        self.assertEqual(
            self.spawn.status.id, 8, 'Spawn status should be STOPPING (8)'
        )

        self.head.refresh_from_db()
        self.assertEqual(
            self.head.status.id, 8, 'Head status should be STOPPING (8)'
        )
