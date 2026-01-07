from hydra.models import HydraEnvironment
from hydra.models import HydraExecutable
from hydra.models import HydraSwitch
from hydra.models import HydraSpawn
from hydra.tasks import build_command
from hydra.models import HydraHead
from hydra.models import HydraSpell
from hydra.models import HydraSpellbook
from hydra.models import HydraSpawnStatus
from hydra.models import HydraHeadStatus
from django.test import TestCase

from environments.models import ProjectEnvironment


class HydraBridgeTest(TestCase):
    def setUp(self):
        # 0. Setup Statuses (Since they are FKs not Strings)
        # Assuming IDs 1-5 for standard lifecycle
        self.status_running = HydraHeadStatus.objects.create(id=1, name='Running')
        self.status_success = HydraHeadStatus.objects.create(id=2, name='Success')
        self.status_failed = HydraHeadStatus.objects.create(id=3, name='Failed')
        self.spawn_status = HydraSpawnStatus.objects.create(id=1, name='Created')

        # 1. Environment
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
        
        # 2. Executable
        self.exe = HydraExecutable.objects.create(
            name="Unreal Automation Tool",
            slug="uat",
            path_template="{engine_root}/Build/BatchFiles/RunUAT.bat"
        )
        
        # 3. Switches
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
        
        # 4. Spellbook & Spell
        self.book = HydraSpellbook.objects.create(name="Daily Build")
        self.spell = HydraSpell.objects.create(name="Clean Build", executable=self.exe)
        self.spell.active_switches.add(self.sw_clean, self.sw_map)
        
        # Link spell to book
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
            status=self.status_running # Initialize with a status
        )
        
        cmd = build_command(hydra_head)
        
        # Assert Path Resolution
        expected_path = "C:/UE_5.6/Build/BatchFiles/RunUAT.bat"
        self.assertEqual(cmd[0], expected_path)
        
        # Assert Switches
        self.assertIn("-clean", cmd)
        
        # Assert Value Switch
        # Should appear as flag then value in list: ..., "-map", "EntryMap", ...
        self.assertIn("-map", cmd)
        self.assertIn("EntryMap", cmd)
        
        # Verify order (flag before value)
        map_idx = cmd.index("-map")
        self.assertEqual(cmd[map_idx + 1], "EntryMap")