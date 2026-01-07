import os
from django.test import TestCase
from hydra.models import HydraExecutable, HydraSwitch, HydraSpell, HydraSpawn, HydraHead, HydraEnvironment, HydraSpellbook, HydraHeadStatus, HydraSpawnStatus
from environments.models import ProjectEnvironment
from hydra.tasks import build_command

class HydraBridgeTest(TestCase):
    def setUp(self):
        self.status_running = HydraHeadStatus.objects.create(id=1, name='Running')
        self.status_success = HydraHeadStatus.objects.create(id=2, name='Success')
        self.status_failed = HydraHeadStatus.objects.create(id=3, name='Failed')
        self.spawn_status = HydraSpawnStatus.objects.create(id=1, name='Created')

        self.proj_env = ProjectEnvironment.objects.create(
            name="TestEnv",
            project_root="C:/MyGame",
            engine_root="C:/UE_5.6",
            build_root="C:/Builds",
            project_name="MyGame"
        )
        self.hydra_env = HydraEnvironment.objects.create(
            name="HydraTestEnv",
            project_environment=self.proj_env
        )
        
        self.exe = HydraExecutable.objects.create(
            name="Unreal Automation Tool",
            slug="uat",
            path_template="{engine_root}/Build/BatchFiles/RunUAT.bat"
        )
        
        self.sw_clean = HydraSwitch.objects.create(
            name="Clean",
            executable=self.exe, 
            flag="-clean"
        )
        self.sw_map = HydraSwitch.objects.create(
            name="MapArg",
            executable=self.exe, 
            flag="-map",
            value="EntryMap"
        )
        
        self.book = HydraSpellbook.objects.create(name="Daily Build")
        self.spell = HydraSpell.objects.create(name="Clean Build", executable=self.exe)
        self.spell.active_switches.add(self.sw_clean, self.sw_map)
        
        self.book.spells.add(self.spell)
        
    def test_command_generation(self):
        """Verify dynamic variable substitution and switch appending."""
        spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            environment=self.hydra_env,
            status=self.spawn_status
        )
        
        hydra_head = HydraHead.objects.create(
            spawn=spawn, 
            spell=self.spell,
            status=self.status_running
        )
        
        cmd = build_command(hydra_head)
        
        # Assert Path Resolution (Normalized for OS)
        expected_path = os.path.normpath("C:/UE_5.6/Build/BatchFiles/RunUAT.bat")
        self.assertEqual(cmd[0], expected_path)
        
        # Assert Switches
        self.assertIn("-clean", cmd)
        self.assertIn("-map", cmd)
        self.assertIn("EntryMap", cmd)
        
        map_idx = cmd.index("-map")
        self.assertEqual(cmd[map_idx + 1], "EntryMap")