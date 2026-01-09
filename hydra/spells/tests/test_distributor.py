import os
from unittest import mock
from django.test import TestCase
from core.models import RemoteTarget
from environments.models import ProjectEnvironment
from hydra.models import (
    HydraHead, HydraSpell, HydraExecutable, HydraSpawn, 
    HydraSpellbook, HydraEnvironment, HydraHeadStatus, HydraSpawnStatus
)
from hydra.spells.distributor import distribute_build_native

class NativeDistributorTest(TestCase):
    def setUp(self):
        # 1. Setup Statuses
        self.status_pending = HydraHeadStatus.objects.create(id=1, name="Pending")
        self.spawn_status = HydraSpawnStatus.objects.create(id=1, name="Running")

        # 2. Setup Environment
        self.proj_env = ProjectEnvironment.objects.create(
            name="Test Env",
            project_root="C:/TestProject",
            engine_root="C:/UE_5.0",
            build_root="C:/TestBuilds",     # Priority 1: C:\TestBuilds\ReleaseTest
            staging_dir="C:/TestStaging",   # Priority 2: C:\TestStaging
            project_name="TestGame",
            is_active=True
        )
        self.hydra_env = HydraEnvironment.objects.create(
            name="Test Hydra Env",
            project_environment=self.proj_env
        )

        self.book = HydraSpellbook.objects.create(name="Distribute Book")
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            environment=self.hydra_env,
            status=self.spawn_status
        )
        
        self.exe = HydraExecutable.objects.create(
            name="Native Dist",
            slug="distribute_fleet",
            path_template="" 
        )
        self.spell = HydraSpell.objects.create(name="Dist Spell", executable=self.exe)
        
        self.head = HydraHead.objects.create(
            spawn=self.spawn,
            spell=self.spell,
            status=self.status_pending
        )

        # 3. Auto-Discovered Agent (No path)
        self.t2 = RemoteTarget.objects.create(
            hostname="AGENT-DISCOVERED", 
            unc_path="", 
            status="ONLINE", 
            is_enabled=True
        )

    @mock.patch('hydra.spells.distributor.os.path.exists')
    @mock.patch('hydra.spells.distributor.subprocess.run')
    def test_distribute_priority_release_test(self, mock_run, mock_exists):
        """Test that distributor prioritizes C:\\TestBuilds\\ReleaseTest (Legacy behavior)."""
        mock_exists.return_value = True # Everything exists
        mock_run.return_value.returncode = 1
        
        exit_code, log = distribute_build_native(self.head)

        self.assertEqual(exit_code, 0)
        
        # Verify it used Priority 1: ReleaseTest
        # Source: C:\TestBuilds\ReleaseTest
        # Dest:   \\AGENT-DISCOVERED\steambuild\ReleaseTest
        
        found_call = False
        expected_dest = "\\\\AGENT-DISCOVERED\\steambuild\\ReleaseTest"
        
        for call in mock_run.call_args_list:
            args = call[0][0]
            dest = args[2]
            if expected_dest in dest:
                found_call = True
                break
        
        self.assertTrue(found_call, f"Did not find expected destination: {expected_dest}")

    @mock.patch('hydra.spells.distributor.os.path.exists')
    @mock.patch('hydra.spells.distributor.subprocess.run')
    def test_distribute_fallback_staging(self, mock_run, mock_exists):
        """Test that distributor falls back to StagingDir if ReleaseTest is missing."""
        
        # Side effect: Returns False for 'ReleaseTest', True for 'TestStaging'
        def side_effect(path):
            if "ReleaseTest" in path:
                return False
            return True
        
        mock_exists.side_effect = side_effect
        mock_run.return_value.returncode = 1
        
        exit_code, log = distribute_build_native(self.head)

        self.assertEqual(exit_code, 0)

        # Verify it used Priority 2: Staging
        # Source: C:\TestStaging
        # Dest:   \\AGENT-DISCOVERED\steambuild\TestStaging
        
        found_call = False
        expected_dest = "\\\\AGENT-DISCOVERED\\steambuild\\TestStaging"
        
        for call in mock_run.call_args_list:
            args = call[0][0]
            dest = args[2]
            if expected_dest in dest:
                found_call = True
                break
        
        self.assertTrue(found_call, f"Did not find fallback destination: {expected_dest}")