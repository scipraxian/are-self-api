from unittest import mock

import pytest
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


class FastValidateIntegrationTest(TestCase):
    # ADDED: Load the brains needed for the signal handlers to work
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
        'frontal_lobe/fixtures/initial_data.json',
    ]

    def setUp(self):
        self.client = Client()

        # We can keep manual creation for Hydra objects if you prefer,
        # or rely on fixtures if you load hydra/fixtures/initial_data.json too.
        # Keeping your manual setup below to minimize changes:
        self.status_created = HydraHeadStatus.objects.get_or_create(
            id=1, defaults={'name': 'Created'}
        )[0]
        self.status_pending = HydraHeadStatus.objects.get_or_create(
            id=2, defaults={'name': 'Pending'}
        )[0]
        self.status_running = HydraHeadStatus.objects.get_or_create(
            id=3, defaults={'name': 'Running'}
        )[0]
        self.status_success = HydraHeadStatus.objects.get_or_create(
            id=4, defaults={'name': 'Success'}
        )[0]
        self.status_failed = HydraHeadStatus.objects.get_or_create(
            id=5, defaults={'name': 'Failed'}
        )[0]

        self.spawn_created = HydraSpawnStatus.objects.get_or_create(
            id=1, defaults={'name': 'Created'}
        )[0]
        self.spawn_running = HydraSpawnStatus.objects.get_or_create(
            id=3, defaults={'name': 'Running'}
        )[0]
        self.spawn_success = HydraSpawnStatus.objects.get_or_create(
            id=4, defaults={'name': 'Success'}
        )[0]
        self.spawn_failed = HydraSpawnStatus.objects.get_or_create(
            id=5, defaults={'name': 'Failed'}
        )[0]

        self.exe = TalosExecutable.objects.create(
            name='TestRunner', executable='Test.exe'
        )
        self.spell = HydraSpell.objects.create(
            name='Run Headless', talos_executable=self.exe
        )
        self.book = HydraSpellbook.objects.create(name='Fast Validate')
        # FIX: Node must be marked as root for Hydra to find it
        self.book.nodes.create(spell=self.spell, is_root=True)

    @mock.patch('hydra.hydra.cast_hydra_spell.delay')
    def test_button_click_launches_process(self, mock_celery):
        mock_celery.return_value.id = '550e8400-e29b-41d4-a716-446655440000'
        # 1. Trigger Request using UUID

        url = reverse('hydra:hydra_launch', args=[self.book.id])

        # Capture commit callbacks
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)

        # 2. Verify Response
        self.assertEqual(response.status_code, 302)
        # FIX: The view redirects to 'hydra:graph_monitor'
        self.assertIn(
            reverse(
                'hydra:graph_monitor',
                args=[HydraSpawn.objects.first().id],
            ),
            response.url,
        )

        # 3. Verify DB
        spawn = HydraSpawn.objects.first()
        self.assertIsNotNone(spawn)
        self.assertEqual(spawn.status.id, HydraSpawnStatus.RUNNING)

        # 4. Verify Celery Handoff
        heads = spawn.heads.all()
        head = heads.first()
        mock_celery.assert_called_once_with(head.id)

    @pytest.mark.live
    @mock.patch('hydra.tasks.check_next_wave.delay')
    def test_spawn_finalizes_when_last_head_succeeds(self, mock_check):
        from hydra.tasks import cast_hydra_spell

        # 1. Setup a spawn with one head
        spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            status_id=HydraSpawnStatus.RUNNING,
        )
        head = HydraHead.objects.create(
            spawn=spawn, spell=self.spell, status_id=HydraHeadStatus.PENDING
        )

        # 2. Run the task
        with (
            mock.patch('hydra.tasks.build_command') as mock_build,
            mock.patch('hydra.tasks.stream_command_to_db') as mock_stream,
        ):
            mock_stream.return_value = 0  # Success

            # --- THE FIX: EXECUTE ON_COMMIT CALLBACKS ---
            with self.captureOnCommitCallbacks(execute=True):
                cast_hydra_spell(head.id)

        # 3. Verify head is Success
        head.refresh_from_db()
        self.assertEqual(head.status_id, HydraHeadStatus.SUCCESS)

        # 4. Trigger check_next_wave logic
        from hydra.tasks import check_next_wave

        check_next_wave(spawn.id)

        # 5. Verify Spawn is SUCCESS
        spawn.refresh_from_db()
        self.assertEqual(spawn.status_id, HydraSpawnStatus.SUCCESS)
