import os
import sys
import unittest
from unittest import mock

import django

# Add current directory to sys.path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import transaction
from django.test import TestCase, TransactionTestCase

from environments.models import ProjectEnvironment
from hydra.hydra import Hydra
from hydra.models import (
    HydraEnvironment,
    HydraExecutable,
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)


class ReproduceRunTwiceTest(TransactionTestCase):
    def setUp(self):
        self.status_created, _ = HydraHeadStatus.objects.get_or_create(id=HydraHeadStatus.CREATED, defaults={'name': 'Created'})
        self.status_running, _ = HydraHeadStatus.objects.get_or_create(id=HydraHeadStatus.RUNNING, defaults={'name': 'Running'})
        self.status_pending, _ = HydraHeadStatus.objects.get_or_create(id=HydraHeadStatus.PENDING, defaults={'name': 'Pending'})
        
        self.proj_env = ProjectEnvironment.objects.create(name="TestEnv")
        self.hydra_env = HydraEnvironment.objects.create(name="H_Env", project_environment=self.proj_env)
        self.book = HydraSpellbook.objects.create(name="Test Book")
        
        self.spawn_status, _ = HydraSpawnStatus.objects.get_or_create(id=HydraSpawnStatus.CREATED, defaults={'name': 'Created'})
        
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, environment=self.hydra_env, status=self.spawn_status
        )
        
        self.exe = HydraExecutable.objects.create(name="Test", slug="test", path_template="test")
        self.spell = HydraSpell.objects.create(name="Spell 1", executable=self.exe, order=1)
        
        self.head = HydraHead.objects.create(
            status=self.status_created, 
            spell=self.spell,
            spawn=self.spawn
        )

    @mock.patch('hydra.hydra.cast_hydra_spell.delay')
    def test_dispatch_twice_repro(self, mock_delay):
        """
        Reproduces the issue where multiple calls to _dispatch_next_wave
        result in the same head being dispatched multiple times.
        """
        controller = Hydra(spawn_id=self.spawn.id)
        
        # Simulate two concurrent calls to _dispatch_next_wave
        # In a real scenario, this could be start() and then a poll() before the first task starts.
        
        with transaction.atomic():
            controller.dispatch_next_wave()
        
        with transaction.atomic():
            controller.dispatch_next_wave()
        
        # Currently, this will likely be 2, because _dispatch_next_wave 
        # doesn't change the status of the head to something other than CREATED.
        print(f"Call count: {mock_delay.call_count}")
        self.assertEqual(mock_delay.call_count, 1, "Should only dispatch once!")

if __name__ == '__main__':
    unittest.main()
