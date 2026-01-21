import os
from django.test import TestCase
from hydra.models import HydraExecutable, HydraSwitch, HydraSpell, HydraSpawn, HydraHead, HydraHeadStatus, HydraSpawnStatus, HydraEnvironment, HydraSpellbook
from hydra.tasks import build_command
from environments.models import ProjectEnvironment

class StagingPathTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]
    def setUp(self):
        self.st_created = HydraHeadStatus.objects.first()
        self.spawn_created = HydraSpawnStatus.objects.first()

        self.env = ProjectEnvironment.objects.create(
            name="ProdEnv",
            project_root="C:/MyGame",
            engine_root="C:/UE5",
            build_root="C:/Builds",
            staging_dir="D:/StagingBuffer",
            project_name="MyGame"
        )
        self.hydra_env = HydraEnvironment.objects.create(project_environment=self.env)

        self.exe_uat = HydraExecutable.objects.create(name="testUAT", slug="testuat", path_template="RunUAT.bat")
        self.sw_stage_dir = HydraSwitch.objects.create(
            executable=self.exe_uat, 
            flag="-stagingdirectory=", 
            value="{staging_dir}"
        )
        self.spell_build = HydraSpell.objects.create(name="Build", executable=self.exe_uat)
        self.spell_build.active_switches.add(self.sw_stage_dir)

        self.exe_game = HydraExecutable.objects.create(
            name="TestGameExe",
            slug="test_game_exe",
            path_template="{staging_dir}/Windows/{project_name}.exe"
        )
        self.spell_run = HydraSpell.objects.create(name="Run", executable=self.exe_game)

    def test_paths_align(self):
        book = HydraSpellbook.objects.create(name="PathTestBook")
        spawn = HydraSpawn.objects.create(
            spellbook=book, 
            environment=self.hydra_env, 
            status=self.spawn_created
        )

        head_build = HydraHead.objects.create(spawn=spawn, spell=self.spell_build, status=self.st_created)
        head_run = HydraHead.objects.create(spawn=spawn, spell=self.spell_run, status=self.st_created)

        cmd_build = build_command(head_build)
        cmd_run = build_command(head_run)

        # VERIFY BUILD OUTPUT PATH
        # Normalizing slashes for Windows check
        expected_arg = os.path.normpath("D:/StagingBuffer")
        # Check if any arg ENDS with the path (to handle -stagingdirectory=D:...)
        found_staging_arg = any(expected_arg in os.path.normpath(arg) for arg in cmd_build)
        self.assertTrue(found_staging_arg, f"Build command missing staging dir! Got: {cmd_build}")

        # VERIFY RUN INPUT PATH
        run_exe = cmd_run[0]
        expected_run_path = os.path.normpath("D:/StagingBuffer/Windows/MyGame.exe")
        self.assertEqual(run_exe, expected_run_path, "Run command has wrong exe path!")