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
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        # 1. Infrastructure
        self.status_created = HydraHeadStatus.objects.create(id=1, name="Created")
        self.status_success = HydraHeadStatus.objects.create(id=4, name="Success")
        
        self.proj_env = ProjectEnvironment.objects.create(
            name="TestEnv", 
            project_root=self.test_dir, 
            engine_root=self.test_dir, 
            build_root=self.test_dir, 
            staging_dir=self.test_dir,
            project_name="TestProject"
        )
        self.hydra_env = HydraEnvironment.objects.create(name="H_Env", project_environment=self.proj_env)
        self.book = HydraSpellbook.objects.create(name="Test Book")
        self.spawn_status = HydraSpawnStatus.objects.create(id=1, name="Created")
        
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, environment=self.hydra_env, status=self.spawn_status
        )

        # 2. Executable & Spell
        self.exe = HydraExecutable.objects.create(
            name="Version Stamper",
            slug="version_stamper",
            path_template=""
        )
        self.spell = HydraSpell.objects.create(name="Stamp Version", executable=self.exe)
        
        # 3. Head
        self.head = HydraHead.objects.create(
            status=self.status_created, 
            spell=self.spell,
            spawn=self.spawn
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
