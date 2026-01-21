from unittest import mock
from django.test import TestCase, Client
from django.urls import reverse
from hydra.models import (
    HydraSpellbook, HydraSpell, HydraExecutable, HydraSwitch, 
    HydraSpawn, HydraHeadStatus, HydraSpawnStatus
)
from environments.models import ProjectEnvironment

class StagingOpsIntegrationTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]
    def setUp(self):
        self.client = Client()
        self.status_created = HydraHeadStatus.objects.first()
        self.status_pending = HydraHeadStatus.objects.get(name="Pending")
        self.status_running = HydraHeadStatus.objects.get(name="Running")
        self.spawn_created = HydraSpawnStatus.objects.first()
        self.spawn_running = HydraSpawnStatus.objects.get(name="Running")

        self.env = ProjectEnvironment.objects.create(
            name="Staging Env", 
            is_active=True,
            project_root="C:/Project",
            engine_root="C:/UE5",
            build_root="C:/Builds",
            staging_dir="C:/Staging"
        )

        self.exe_uat = HydraExecutable.objects.create(name="test UAT", slug="test_uat", path_template="RunUAT.bat")
        self.exe_game = HydraExecutable.objects.create(name="tes Game", slug="test_game", path_template="Game.exe")
        
        self.spell_build = HydraSpell.objects.create(name="TestStaging: Build Game", executable=self.exe_uat, order=10)
        self.spell_run = HydraSpell.objects.create(name="TestStaging: Record PSOs", executable=self.exe_game, order=20)
        
        self.book = HydraSpellbook.objects.create(name="tes Staging Operations")
        self.book.spells.add(self.spell_build, self.spell_run)

    @mock.patch('hydra.hydra.cast_hydra_spell.delay')
    def test_launch_respects_ordering(self, mock_celery):
        # 1. Trigger Request via UUID
        url = reverse('hydra_launch', args=[self.book.id])
        
        # CRITICAL: Execute on_commit callbacks
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        # 2. Verify Spawn State
        spawn = HydraSpawn.objects.first()
        heads = spawn.heads.all().order_by('spell__order')
        self.assertEqual(heads.count(), 2)
        
        head_build = heads[0]

        # 3. Verify Wave Dispatch
        mock_celery.assert_called_once()
        called_args = mock_celery.call_args
        self.assertEqual(called_args[0][0], head_build.id)