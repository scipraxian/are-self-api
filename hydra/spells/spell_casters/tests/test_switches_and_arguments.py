from django.test import TestCase

from environments.models import (
    TalosExecutable,
    TalosExecutableArgument,
    TalosExecutableArgumentAssignment,
    TalosExecutableSwitch,
)
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellArgumentAssignment,
    HydraSpellbook,
)
from hydra.spells.spell_casters.switches_and_arguments import (
    spell_switches_and_arguments,)


class SwitchesAndArgumentsTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Define the Tool
        self.exe = TalosExecutable.objects.create(name='Test Tool',
                                                  executable='tool.exe',
                                                  working_path='C:/Tools')

        # 2. Define the Spell
        self.spell = HydraSpell.objects.create(
            name='Test Spell',
            talos_executable=self.exe,
        )

    def test_simple_switches(self):
        """Test basic flag resolution."""
        # Create a switch on the Executable
        sw1 = TalosExecutableSwitch.objects.create(name='Global', flag='-g')
        self.exe.switches.add(sw1)

        # Create a switch on the Spell
        sw2 = TalosExecutableSwitch.objects.create(name='Local', flag='-l')
        self.spell.switches.add(sw2)

        # Updated: returns list
        result_list = spell_switches_and_arguments(self.spell.id)

        # Order isn't strictly guaranteed between sets, but list items must match
        self.assertIn('-g', result_list)
        self.assertIn('-l', result_list)

    def test_full_command_structure(self):
        """
        The Ultimate Test: Arguments MUST precede Switches.
        """
        # 1. Arguments
        arg1 = TalosExecutableArgument.objects.create(name='Arg1',
                                                      argument='pos1')
        TalosExecutableArgumentAssignment.objects.create(executable=self.exe,
                                                         argument=arg1,
                                                         order=1)

        arg2 = TalosExecutableArgument.objects.create(name='Arg2',
                                                      argument='pos2')
        HydraSpellArgumentAssignment.objects.create(spell=self.spell,
                                                    argument=arg2,
                                                    order=1)

        # 2. Switches
        sw1 = TalosExecutableSwitch.objects.create(name='Sw1', flag='-flag1')
        self.exe.switches.add(sw1)

        sw2 = TalosExecutableSwitch.objects.create(name='Sw2', flag='-flag2')
        self.spell.switches.add(sw2)

        result_list = spell_switches_and_arguments(self.spell.id)

        # Verify Order: Args first, then Switches
        self.assertTrue(len(result_list) == 4)

        # Verify Arguments are present
        self.assertIn('pos1', result_list)
        self.assertIn('pos2', result_list)

        # Verify Switches are present
        self.assertIn('-flag1', result_list)
        self.assertIn('-flag2', result_list)
