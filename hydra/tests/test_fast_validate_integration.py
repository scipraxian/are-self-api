import json
from unittest import mock
from django.test import TestCase, Client
from django.urls import reverse
from hydra.models import (
    HydraSpellbook, HydraSpell, HydraExecutable, HydraSwitch,
    HydraSpawn, HydraHeadStatus, HydraSpawnStatus, HydraHead
)
from environments.models import ProjectEnvironment


class FastValidateIntegrationTest(TestCase):
    # ADDED: Load the brains needed for the signal handlers to work
    fixtures = [
        'talos_reasoning/fixtures/initial_data.json',
        'talos_frontal/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.client = Client()

        # We can keep manual creation for Hydra objects if you prefer,
        # or rely on fixtures if you load hydra/fixtures/initial_data.json too.
        # Keeping your manual setup below to minimize changes:
        self.status_created = HydraHeadStatus.objects.get_or_create(id=1, defaults={'name': "Created"})[0]
        self.status_pending = HydraHeadStatus.objects.get_or_create(id=2, defaults={'name': "Pending"})[0]
        self.status_running = HydraHeadStatus.objects.get_or_create(id=3, defaults={'name': "Running"})[0]
        self.status_success = HydraHeadStatus.objects.get_or_create(id=4, defaults={'name': "Success"})[0]
        self.status_failed = HydraHeadStatus.objects.get_or_create(id=5, defaults={'name': "Failed"})[0]

        self.spawn_created = HydraSpawnStatus.objects.get_or_create(id=1, defaults={'name': "Created"})[0]
        self.spawn_running = HydraSpawnStatus.objects.get_or_create(id=3, defaults={'name': "Running"})[0]
        self.spawn_success = HydraSpawnStatus.objects.get_or_create(id=4, defaults={'name': "Success"})[0]
        self.spawn_failed = HydraSpawnStatus.objects.get_or_create(id=5, defaults={'name': "Failed"})[0]

        self.env = ProjectEnvironment.objects.create(
            name="Integration Env",
            is_active=True,
            project_root="C:/FakeProject"
        )
        from hydra.models import HydraEnvironment
        self.hydra_env = HydraEnvironment.objects.create(project_environment=self.env, name="TestEnv")

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

        # 2. Verify Response
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('hydra_spawn_monitor', args=[HydraSpawn.objects.first().id]), response.url)

        # 3. Verify DB
        spawn = HydraSpawn.objects.first()
        self.assertIsNotNone(spawn)
        self.assertEqual(spawn.status.id, HydraSpawnStatus.RUNNING)

        # 4. Verify Celery Handoff
        heads = spawn.heads.all()
        head = heads.first()
        mock_celery.assert_called_once_with(head.id)

    @mock.patch('hydra.tasks.check_next_wave.delay')
    def test_spawn_finalizes_when_last_head_succeeds(self, mock_check):
        from hydra.hydra import Hydra
        from hydra.tasks import cast_hydra_spell

        # 1. Setup a spawn with one head
        spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            environment=self.hydra_env,
            status_id=HydraSpawnStatus.RUNNING
        )
        head = HydraHead.objects.create(
            spawn=spawn,
            spell=self.spell,
            status_id=HydraHeadStatus.PENDING
        )

        # 2. Run the task
        with mock.patch('hydra.tasks.build_command') as mock_build, \
                mock.patch('hydra.tasks.stream_command_to_db') as mock_stream:
            mock_stream.return_value = 0  # Success
            cast_hydra_spell(head.id)

        # 3. Verify head is Success
        head.refresh_from_db()
        self.assertEqual(head.status_id, HydraHeadStatus.SUCCESS)

        # 4. Manually trigger check_next_wave logic
        from hydra.tasks import check_next_wave
        check_next_wave(spawn.id)

        # 5. Verify Spawn is SUCCESS
        spawn.refresh_from_db()
        self.assertEqual(spawn.status_id, HydraSpawnStatus.SUCCESS)

    def test_active_spawn_blocking_new_launch(self):
        # 1. Setup an active spawn
        spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            environment=self.hydra_env,
            status_id=HydraSpawnStatus.RUNNING
        )
        HydraHead.objects.create(
            spawn=spawn,
            spell=self.spell,
            status_id=HydraHeadStatus.RUNNING
        )

        # 2. Try to launch again
        url = reverse('hydra_launch', args=[self.book.id])
        response = self.client.post(url)

        # 3. Should redirect to existing monitor
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('hydra_spawn_monitor', args=[spawn.id]), response.url)
        self.assertEqual(HydraSpawn.objects.count(), 1)