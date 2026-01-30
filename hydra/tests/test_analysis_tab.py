from django.test import TestCase, Client
from django.urls import reverse
from hydra.models import HydraHead, HydraSpawn, HydraSpellbook, HydraSpawnStatus, HydraHeadStatus, \
    HydraSpell
from talos_frontal.models import ConsciousStream, ConsciousStatusID
from environments.models import TalosExecutable


class AnalysisTabTest(TestCase):
    # Load all fixtures to ensure IDs exist
    fixtures = [
        'environments/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'talos_frontal/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.client = Client()
        # Setup infrastructure
        self.book = HydraSpellbook.objects.create(name="TabBook")

        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.SUCCESS)

        self.exe = TalosExecutable.objects.create(name="TabExe",
                                                  executable="tab.exe")
        self.spell = HydraSpell.objects.create(name="TabSpell",
                                               talos_executable=self.exe)

        self.head = HydraHead.objects.create(spawn=self.spawn,
                                             spell=self.spell,
                                             status_id=HydraHeadStatus.SUCCESS)

    def test_analysis_tab_empty(self):
        """Verify tab shows 'No analysis' message when no thought is linked."""
        url = reverse('hydra_head_analysis', args=[self.head.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No neural analysis available yet")

    def test_analysis_tab_content(self):
        """Verify tab renders markdown content when thought is linked."""
        # Create a thought linked specifically to this head
        ConsciousStream.objects.create(
            spawn_link=self.spawn,
            head_link=self.head,  # <--- CRITICAL LINK
            current_thought="**System Verified.** No anomalies detected.",
            status_id=ConsciousStatusID.DONE,
            model_name="test-model-v1",
            tokens_input=50,
            tokens_output=10)

        url = reverse('hydra_head_analysis', args=[self.head.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Check for rendered HTML (bold tag from markdown)
        self.assertContains(response, "<strong>System Verified.</strong>")
        # Check for metrics footer
        self.assertContains(response, "test-model-v1")
        self.assertContains(response, "50 In / 10 Out")
