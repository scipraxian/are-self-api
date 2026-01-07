import json
from unittest import mock
from django.test import TestCase, Client
from django.urls import reverse
from hydra.models import (
    HydraSpellbook, HydraSpell, HydraExecutable, HydraSwitch, 
    HydraSpawn, HydraHeadStatus, HydraSpawnStatus
)
from environments.models import ProjectEnvironment

class FastValidateIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()
        
        # 1. Setup Status Constants (Prerequisite)
        self.status_created = HydraHeadStatus.objects.create(id=1, name="Created")
        self.status_running = HydraHeadStatus.objects.create(id=3, name="Running")
        self.spawn_created = HydraSpawnStatus.objects.create(id=1, name="Created")
        self.spawn_running = HydraSpawnStatus.objects.create(id=3, name="Running")

        # 2. Setup Environment
        self.env = ProjectEnvironment.objects.create(
            name="Integration Env", 
            is_active=True,
            project_root="C:/FakeProject"
        )

        # 3. Setup The "Fast Validate" Spellbook Data
        # Executable
        self.exe = HydraExecutable.objects.create(
            name="TestRunner", 
            slug="test_runner",
            path_template="Test.exe"
        )
        
        # Spell
        self.spell = HydraSpell.objects.create(
            name="Run Headless",
            executable=self.exe
        )
        
        # Book
        self.book = HydraSpellbook.objects.create(name="Fast Validate")
        self.book.spells.add(self.spell)

    @mock.patch('hydra.hydra.cast_hydra_spell.delay')
    def test_button_click_launches_process(self, mock_celery):
        """
        Simulates the user clicking the 'Fast Validate' button.
        Verifies:
        1. View returns 200 OK and uses the correct template.
        2. HydraSpawn is created in DB.
        3. HydraHead is created for the spell.
        4. Celery task is triggered for that Head.
        """
        # 1. Trigger Request
        url = reverse('hydra_launch_fast_validate')
        response = self.client.post(url)

        # 2. Verify Response
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'hydra/partials/spawn_feedback.html')
        self.assertContains(response, "Hydra Protocol Initiated")

        # 3. Verify Database State (The Controller Logic)
        spawn = HydraSpawn.objects.first()
        self.assertIsNotNone(spawn, "HydraSpawn was not created!")
        self.assertEqual(spawn.status.id, HydraSpawnStatus.RUNNING, "Spawn should be set to RUNNING")
        
        # Verify Heads
        heads = spawn.heads.all()
        self.assertEqual(heads.count(), 1, "Should have generated 1 Head from the Spellbook")
        head = heads.first()
        self.assertEqual(head.spell.name, "Run Headless")

        # 4. Verify Celery Handoff
        # The controller calls cast_hydra_spell.delay(head.id)
        mock_celery.assert_called_once_with(head.id)
        
        print(f"\n[TEST] Success! Button generated Spawn {spawn.id} and queued Head {head.id} to Celery.")