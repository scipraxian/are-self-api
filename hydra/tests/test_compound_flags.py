import os
from django.test import TestCase
from hydra.models import (
    HydraExecutable, HydraSwitch, HydraSpell, HydraSpawn, HydraHead, 
    HydraHeadStatus, HydraSpawnStatus, HydraEnvironment, HydraSpellbook
)
from hydra.tasks import build_command
from environments.models import ProjectEnvironment

class CompoundFlagTest(TestCase):
    def setUp(self):
        # 1. Setup Environment
        self.env = ProjectEnvironment.objects.create(
            name="FlagTestEnv",
            project_root="C:/Proj",
            engine_root="C:/UE5",
            build_root="C:/Builds",
            project_name="TestGame"
        )
        self.hydra_env = HydraEnvironment.objects.create(project_environment=self.env)
        
        self.status_created = HydraHeadStatus.objects.create(id=1, name='Created')
        self.spawn_created = HydraSpawnStatus.objects.create(id=1, name='Created')

        # 2. Setup Tool
        self.exe = HydraExecutable.objects.create(
            name="UAT", 
            slug="uat", 
            path_template="RunUAT.bat"
        )

        # 3. Setup The Problematic Switch (Compound Flags)
        self.sw_compound = HydraSwitch.objects.create(
            name="BuildCookStagePak",  # Added Unique Name
            executable=self.exe, 
            flag="-build -cook -stage -pak", 
            value="" 
        )
        
        # 4. Setup Normal Switch (Control Group)
        self.sw_normal = HydraSwitch.objects.create(
            name="Clean",  # Added Unique Name
            executable=self.exe,
            flag="-clean",
            value=""
        )

        # 5. Setup Switch with Value (Control Group)
        self.sw_value = HydraSwitch.objects.create(
            name="Project",  # Added Unique Name
            executable=self.exe,
            flag="-project=",
            value="{project_root}/Game.uproject"
        )

        self.spell = HydraSpell.objects.create(name="Build", executable=self.exe)
        self.spell.active_switches.add(self.sw_compound, self.sw_normal, self.sw_value)
        
        self.book = HydraSpellbook.objects.create(name="Flag Book")
        self.spawn = HydraSpawn.objects.create(spellbook=self.book, environment=self.hydra_env, status=self.spawn_created)
        self.head = HydraHead.objects.create(spawn=self.spawn, spell=self.spell, status=self.status_created)

    def test_flags_are_split(self):
        """
        Verifies that a switch containing spaces is split into individual 
        command arguments, rather than being passed as a single quoted string.
        """
        cmd = build_command(self.head)
        
        print(f"\nGenerated Command List: {cmd}")

        # 1. Assert Normal Flags exist
        self.assertIn("-clean", cmd)
        
        # 2. Assert Value Flags exist
        # Normalize slashes for comparison
        normalized_cmd = [arg.replace("\\", "/") for arg in cmd]
        project_arg = next((arg for arg in normalized_cmd if arg.startswith("-project=")), None)
        
        self.assertIsNotNone(project_arg, "Project argument missing!")
        self.assertIn("C:/Proj/Game.uproject", project_arg)

        # 3. CRITICAL: Assert Compound Flags are SPLIT
        self.assertIn("-build", cmd, "Compound flag '-build' was not split!")
        self.assertIn("-cook", cmd, "Compound flag '-cook' was not split!")
        self.assertIn("-pak", cmd, "Compound flag '-pak' was not split!")

        # 4. Assert the "Ghost" doesn't exist
        self.assertNotIn("-build -cook -stage -pak", cmd, "Command list contains the raw compound string!")