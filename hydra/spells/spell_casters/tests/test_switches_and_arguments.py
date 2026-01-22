from django.test import TestCase
from environments.models import (
    ProjectEnvironment, TalosExecutable, TalosExecutableArgument,
    TalosExecutableArgumentAssignment, TalosExecutableSwitch
)
from hydra.models import (
    HydraSpellbook, HydraSpawn, HydraHead, HydraSpell,
    HydraHeadStatus, HydraSpawnStatus, HydraSpellArgumentAssignment
)
from hydra.spells.spell_casters.switches_and_arguments import spell_switches_and_arguments


class SwitchesAndArgumentsTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json'
    ]

    def setUp(self):
        # 1. Setup Infrastructure
        self.proj_env = ProjectEnvironment.objects.create(
            name="TestEnv",
            project_root="C:/Project",
            engine_root="C:/Engine",
            build_root="C:/Builds",
            is_active=True
        )

        # 2. Define the Tool
        self.exe = TalosExecutable.objects.create(
            name="Test Tool",
            executable="tool.exe",
            working_path="C:/Tools"
        )

        # 3. Define the Spell
        self.spell = HydraSpell.objects.create(
            name="Test Spell",
            talos_executable=self.exe,
            order=1
        )

        # 4. Runtime State
        self.book = HydraSpellbook.objects.create(name="TestBook")
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            status_id=HydraSpawnStatus.CREATED
        )
        self.head = HydraHead.objects.create(
            spawn=self.spawn,
            spell=self.spell,
            status_id=HydraHeadStatus.CREATED
        )

    def test_resolve_arguments_executable_only(self):
        """Verify arguments attached to the TalosExecutable."""
        arg = TalosExecutableArgument.objects.create(name="Script", argument="main.py")
        TalosExecutableArgumentAssignment.objects.create(
            executable=self.exe,
            argument=arg,
            order=1
        )

        result = spell_switches_and_arguments(self.spell.id)
        self.assertEqual(result, "main.py")

    def test_resolve_arguments_spell_only(self):
        """Verify arguments attached to the HydraSpell."""
        arg = TalosExecutableArgument.objects.create(name="Target", argument="BuildTarget")
        HydraSpellArgumentAssignment.objects.create(
            spell=self.spell,
            argument=arg,
            order=1
        )

        result = spell_switches_and_arguments(self.spell.id)
        self.assertEqual(result, "BuildTarget")

    def test_resolve_arguments_combined_ordering(self):
        """
        CRITICAL: Verify Executable Arguments come BEFORE Spell Arguments.
        """
        # 1. Global: script.py
        arg_global = TalosExecutableArgument.objects.create(name="Script", argument="script.py")
        TalosExecutableArgumentAssignment.objects.create(
            executable=self.exe,
            argument=arg_global,
            order=1
        )

        # 2. Local: production
        arg_local = TalosExecutableArgument.objects.create(name="Target", argument="production")
        HydraSpellArgumentAssignment.objects.create(
            spell=self.spell,
            argument=arg_local,
            order=1
        )

        result = spell_switches_and_arguments(self.spell.id)
        self.assertEqual(result, "script.py production")

    def test_resolve_switches_combined(self):
        """Verify both global and local switches are included."""
        sw1 = TalosExecutableSwitch.objects.create(name="Global", flag="-g")
        self.exe.switches.add(sw1)

        sw2 = TalosExecutableSwitch.objects.create(name="Local", flag="-l")
        self.spell.switches.add(sw2)

        result = spell_switches_and_arguments(self.spell.id)

        # Order of switches isn't guaranteed by sets, but both must exist
        self.assertIn("-g", result)
        self.assertIn("-l", result)

    def test_full_command_structure(self):
        """
        The Ultimate Test: Arguments MUST precede Switches.
        """
        # 1. Arguments
        arg1 = TalosExecutableArgument.objects.create(name="Arg1", argument="pos1")
        TalosExecutableArgumentAssignment.objects.create(executable=self.exe, argument=arg1, order=1)

        arg2 = TalosExecutableArgument.objects.create(name="Arg2", argument="pos2")
        HydraSpellArgumentAssignment.objects.create(spell=self.spell, argument=arg2, order=1)

        # 2. Switches
        sw1 = TalosExecutableSwitch.objects.create(name="Sw1", flag="-flag1")
        self.exe.switches.add(sw1)

        sw2 = TalosExecutableSwitch.objects.create(name="Sw2", flag="-flag2")
        self.spell.switches.add(sw2)

        result = spell_switches_and_arguments(self.spell.id)

        # Verify Structure: pos1 pos2 ... -flag1 ...
        parts = result.split()

        self.assertEqual(parts[0], "pos1")
        self.assertEqual(parts[1], "pos2")
        self.assertIn("-flag1", result)
        self.assertIn("-flag2", result)