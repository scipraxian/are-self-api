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
        self.status_created = HydraHeadStatus.objects.create(id=1, name="Created")
        self.status_pending = HydraHeadStatus.objects.create(id=2, name="Pending")
        self.status_running = HydraHeadStatus.objects.create(id=3, name="Running")
        self.spawn_created = HydraSpawnStatus.objects.create(id=1, name="Created")
        self.spawn_running = HydraSpawnStatus.objects.create(id=3, name="Running")

        self.env = ProjectEnvironment.objects.create(
            name="Integration Env", 
            is_active=True,
            project_root="C:/FakeProject"
        )

        self.exe = HydraExecutable.objects.create(name="TestRunner", slug="test_runner", path_template="Test.exe")
        self.spell = HydraSpell.objects.create(name="Run Headless", executable=self.exe)
        self.book = HydraSpellbook.objects.create(name="Fast Validate")
        self.book.spells.add(self.spell)

    @mock.patch('hydra.hydra.cast_hydra_spell.delay')
    def test_button_click_launches_process(self, mock_celery):
        # 1. Trigger Request using UUID
        url = reverse('hydra_launch', args=[self.book.id])
        
        # Capture commit callbacks
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)

        # 2. Verify Response (Updated to expect Monitor)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'hydra/spawn_monitor.html') 
        self.assertContains(response, "OPERATION: Fast Validate")

        # 3. Verify DB
        spawn = HydraSpawn.objects.first()
        self.assertIsNotNone(spawn)
        self.assertEqual(spawn.status.id, HydraSpawnStatus.RUNNING)
        
        # 4. Verify Celery Handoff
        heads = spawn.heads.all()
        head = heads.first()
        mock_celery.assert_called_once_with(head.id)