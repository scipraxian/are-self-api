import json
import os
import shutil
import tempfile
from unittest import mock
from django.test import TestCase

from hydra.models import (
    HydraHead, HydraSpell, HydraExecutable, HydraHeadStatus, 
    HydraSpawn, HydraSpellbook, HydraEnvironment, HydraSpawnStatus,
    HydraSwitch
)
from hydra.spells.version_stamper import version_stamp_native
from environments.models import ProjectEnvironment

class VersionStamperTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

        # 1. Setup Models
        self.status_created = HydraHeadStatus.objects.first()
        self.status_success = HydraHeadStatus.objects.get(name="Success")

        # Create the Env pointing to TEMP dir
        self.proj_env = ProjectEnvironment.objects.create(
            name="TestEnv",
            project_root=self.test_dir,
            engine_root=self.test_dir,
            build_root=self.test_dir,
            staging_dir=self.test_dir,
            project_name="TestProject"
        )

        # Create Hydra Env linking to Project Env
        self.hydra_env = HydraEnvironment.objects.create(
            project_environment=self.proj_env
        )

        self.spellbook = HydraSpellbook.objects.first()

        # Create Spawn linking to Hydra Env
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.spellbook,
            environment=self.hydra_env,
            status=HydraSpawnStatus.objects.get(pk=1)
        )

        self.exe = HydraExecutable.objects.first()
        self.spell = HydraSpell.objects.create(
            name="Version Stamp",
            executable=self.exe,
            order=1
        )

        # Create Head linking to Spawn
        self.head = HydraHead.objects.create(
            spawn=self.spawn,
            spell=self.spell,
            status=self.status_created
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_version_stamp_creates_file(self):
        """Verify that version_stamp_native creates the JSON file if it doesn't exist."""
        target_file = os.path.join(self.test_dir, "Content", "AppVersion.json")
        
        exit_code, log = version_stamp_native(self.head)
        
        self.assertEqual(exit_code, 0)
        self.assertTrue(os.path.exists(target_file))
        
        with open(target_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        self.assertIn('Build', data)
        self.assertIn('Hash', data['Build'])
        self.assertEqual(data['Game']['Name'], "TestProject")

    def test_version_stamp_preserves_data(self):
        """Verify that it preserves existing Game version data."""
        os.makedirs(os.path.join(self.test_dir, "Content"), exist_ok=True)
        target_file = os.path.join(self.test_dir, "Content", "AppVersion.json")
        
        initial_data = {
            "Game": {
                "Name": "OriginalName",
                "Major": 1,
                "Minor": 2,
                "Patch": 3,
                "Label": "GOLD"
            }
        }
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f)
            
        exit_code, log = version_stamp_native(self.head)
        
        self.assertEqual(exit_code, 0)
        
        with open(target_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        self.assertEqual(data['Game']['Major'], 1)
        self.assertEqual(data['Game']['Minor'], 2)
        self.assertEqual(data['Game']['Patch'], 3)
        self.assertEqual(data['Game']['Label'], "GOLD")
        self.assertIn('Build', data)

    def test_custom_path_via_switch(self):
        """Verify that a custom path can be provided via a switch."""
        custom_file = os.path.join(self.test_dir, "CustomVersion.json")
        
        # Add switch to spell
        switch = HydraSwitch.objects.create(
            name="Custom Path",
            executable=self.exe,
            flag="--path",
            value="{project_root}/CustomVersion.json"
        )
        self.spell.active_switches.add(switch)
        
        exit_code, log = version_stamp_native(self.head)
        
        self.assertEqual(exit_code, 0)
        self.assertTrue(os.path.exists(custom_file))
        
        with open(custom_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn('Build', data)
