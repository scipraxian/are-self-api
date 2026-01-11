from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from environments.models import ProjectEnvironment
from hydra.models import HydraSpawn, HydraSpellbook, HydraEnvironment, HydraSpawnStatus
from talos_frontal.models import ConsciousStream, ConsciousStatusID


class NeuralMonitorTest(TestCase):
    # Load fixtures to ensure Status IDs exist
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.client = Client()
        self.url = reverse('neural_status')

        # Infrastructure for ForeignKeys
        self.env = ProjectEnvironment.objects.create(name="TestEnv", is_active=True)
        self.hydra_env = HydraEnvironment.objects.create(project_environment=self.env)
        self.book = HydraSpellbook.objects.create(name="TestBook")

        # We need a Spawn to attach thoughts to
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            environment=self.hydra_env,
            status_id=HydraSpawnStatus.CREATED
        )

    def test_monitor_empty_state(self):
        """Verify the monitor renders the 'Standing by' state when no thoughts exist."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Neural Core Online")
        self.assertNotContains(response, "TALOS:")

    def test_monitor_active_thought(self):
        """Verify the monitor displays the latest thought."""
        # Create an old thought
        ConsciousStream.objects.create(
            spawn_link=self.spawn,
            current_thought="Old thought",
            status_id=ConsciousStatusID.DONE,
            created=timezone.now() - timezone.timedelta(hours=1)
        )

        # Create a new thought
        ConsciousStream.objects.create(
            spawn_link=self.spawn,
            current_thought="Analyzing log entropy...",
            status_id=ConsciousStatusID.THINKING
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        # 1. Check Content
        self.assertContains(response, "Analyzing log entropy...")

        # 2. Check Visual State (Thinking = Yellow Pulse)
        self.assertContains(response, "animation: pulse")

        # 3. Check Ordering (Should not see "Old thought")
        self.assertNotContains(response, "Old thought")

    def test_monitor_integration_with_home(self):
        """Verify the Home page actually includes the HTMX trigger."""
        response = self.client.get(reverse('home'))

        self.assertContains(response, 'hx-get="/neural-status/"')
        self.assertContains(response, 'hx-trigger="every 5s"')
