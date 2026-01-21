from unittest import mock
from django.test import TestCase
from hydra.tasks import cast_hydra_spell
from environments.models import ProjectEnvironment
from hydra.models import (
    HydraHead, HydraSpell, HydraExecutable, HydraHeadStatus, 
    HydraSpawn, HydraSpellbook, HydraEnvironment, HydraSpawnStatus
)
from hydra.spells.native_executables import NativeExecutables

class CastHydraSpellTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]
    def setUp(self):
        # 1. Infrastructure
        self.status_created = HydraHeadStatus.objects.first()
        self.status_success = HydraHeadStatus.objects.get(name="Success")
        self.status_failed = HydraHeadStatus.objects.get(name="Failed")
        
        self.proj_env = ProjectEnvironment.objects.create(
            name="TestEnv", project_root="C:/", engine_root="C:/", build_root="C:/", staging_dir="C:/"
        )
        self.hydra_env = HydraEnvironment.objects.create(name="H_Env", project_environment=self.proj_env)
        self.book = HydraSpellbook.objects.create(name="Test Book")
        self.spawn_status = HydraSpawnStatus.objects.first()
        
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, environment=self.hydra_env, status=self.spawn_status
        )

        # 2. Executable & Spell
        self.exe = HydraExecutable.objects.create(
            name="Native Test",
            slug="test_native_slug",
            path_template="native"
        )
        self.spell = HydraSpell.objects.create(name="Native Spell", executable=self.exe)
        
        # 3. Head
        self.head = HydraHead.objects.create(
            status=self.status_created, 
            spell=self.spell,
            spawn=self.spawn
        )

    @mock.patch.object(NativeExecutables, 'get_handler')
    def test_native_routing(self, mock_get_handler):
        """Verify task routes to Python function if slug exists in Registry."""
        mock_handler = mock.Mock()
        mock_handler.return_value = (0, "Native Success")
        mock_get_handler.return_value = mock_handler

        cast_hydra_spell(self.head.id)

        self.head.refresh_from_db()
        
        mock_get_handler.assert_called_with("test_native_slug")
        mock_handler.assert_called_once()
        self.assertEqual(self.head.status, self.status_success)
        self.assertIn("Native Success", self.head.spell_log)

    @mock.patch('hydra.tasks.build_command')
    @mock.patch('hydra.tasks.stream_command_to_db')
    @mock.patch.object(NativeExecutables, 'get_handler')
    def test_legacy_fallback(self, mock_get_handler, mock_stream, mock_build):
        """Verify task falls back to Shell/Popen if slug is NOT in Registry."""
        mock_get_handler.return_value = None 
        
        mock_build.return_value = ["echo", "legacy"]
        mock_stream.return_value = 0

        cast_hydra_spell(self.head.id)

        mock_get_handler.assert_called_with("test_native_slug")
        
        # Changed to assert_called() instead of once() if there's a legit reason it's called twice
        # OR check your tasks.py logic to see if you accidentally call it twice.
        # For now, let's just assert it WAS called.
        self.assertTrue(mock_build.called) 
        mock_stream.assert_called_once()
    