from django.test import TestCase

from environments.models import (
    ContextVariable,
    ProjectEnvironment,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
    TalosExecutable,
    TalosExecutableArgument,
)
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellArgumentAssignment,
    HydraSpellbook,
    HydraSpellbookNode,
)
from hydra.spells.spell_casters.switches_and_arguments import (
    spell_switches_and_arguments,
)


class SwitchesAndArgumentsTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Setup Base Objects
        self.exe = TalosExecutable.objects.create(
            name='Test Tool', executable='tool.exe', working_path='C:/Tools'
        )
        self.spell = HydraSpell.objects.create(
            name='Test Spell',
            talos_executable=self.exe,
        )
        self.book = HydraSpellbook.objects.create(name='Test Book')
        self.status_created = HydraSpawnStatus.objects.get(id=1)
        self.head_status = HydraHeadStatus.objects.get(id=1)

        # 2. Setup Environments
        self.type_ue = ProjectEnvironmentType.objects.create(name='UE5')
        self.status_active = ProjectEnvironmentStatus.objects.create(
            name='Active'
        )

        self.env_default = ProjectEnvironment.objects.create(
            name='Default Env', type=self.type_ue, status=self.status_active
        )
        self.env_spawn = ProjectEnvironment.objects.create(
            name='Spawn Env', type=self.type_ue, status=self.status_active
        )
        self.env_node = ProjectEnvironment.objects.create(
            name='Node Env', type=self.type_ue, status=self.status_active
        )

        # 3. Setup Variables
        self.var_root = ContextVariable.objects.create(
            environment_id=self.env_default.id,
            key='project_root', value='C:/Default'
        )

        # Link variable to environments with different values
        # We need distinct variable objects or we rely on the link?
        # The schema uses ManyToMany via 'ProjectEnvironmentContext' which links Env <-> Var.
        # To test overrides, we usually create different variables or different values.
        # Since the key comes from the variable, let's create specific variables for the test.

        self.var_root_default = self._create_var('project_root', 'C:/Default')
        self.var_root_spawn = self._create_var('project_root', 'C:/Spawn')
        self.var_root_node = self._create_var('project_root', 'C:/Node')

        self._link_env(self.env_default, self.var_root_default)
        self._link_env(self.env_spawn, self.var_root_spawn)
        self._link_env(self.env_node, self.var_root_node)

        # 4. Create Argument using the token
        self.arg = TalosExecutableArgument.objects.create(
            name='Project Flag', argument='-project={{ project_root }}'
        )
        HydraSpellArgumentAssignment.objects.create(
            spell=self.spell, argument=self.arg, order=1
        )

    def _create_var(self, key, value):
        return ContextVariable.objects.create(
            name=f'{key}_{value}', key=key, value=value
        )

    def _link_env(self, env, var):
        ContextVariable.objects.create(environment=env, context_variable=var)

    def test_legacy_mode(self):
        """Verifies calling with just spell_id works (no context)."""
        result = spell_switches_and_arguments(spell_id=self.spell.id)
        # Should render empty string for missing variable or literal
        self.assertIn('-project=', result[0])

    def test_tier_3_book_default(self):
        """Verify fallback to Spellbook default environment."""
        self.book.environment = self.env_default
        self.book.save()

        spawn = HydraSpawn.objects.create(
            spellbook=self.book, status=self.status_created
        )
        head = HydraHead.objects.create(
            spawn=spawn, spell=self.spell, status=self.head_status
        )

        result = spell_switches_and_arguments(head_id=head.id)
        self.assertIn('-project=C:/Default', result)

    def test_tier_2_spawn_selection(self):
        """Verify Spawn environment overrides Book default."""
        self.book.environment = self.env_default
        self.book.save()

        spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            status=self.status_created,
            environment=self.env_spawn,  # <--- Selection
        )
        head = HydraHead.objects.create(
            spawn=spawn, spell=self.spell, status=self.head_status
        )

        result = spell_switches_and_arguments(head_id=head.id)
        self.assertIn('-project=C:/Spawn', result)

    def test_tier_1_node_override(self):
        """Verify Node environment overrides Spawn and Book."""
        self.book.environment = self.env_default
        self.book.save()

        spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            status=self.status_created,
            environment=self.env_spawn,
        )

        node = HydraSpellbookNode.objects.create(
            spellbook=self.book,
            spell=self.spell,
            environment=self.env_node,  # <--- Override
        )

        head = HydraHead.objects.create(
            spawn=spawn, spell=self.spell, node=node, status=self.head_status
        )

        result = spell_switches_and_arguments(head_id=head.id)
        self.assertIn('-project=C:/Node', result)

    def test_metadata_injection(self):
        """Verify metadata keys (head_id, etc) are available."""
        # Create argument expecting metadata
        arg_meta = TalosExecutableArgument.objects.create(
            name='Meta', argument='-id={{ head_id }}'
        )
        HydraSpellArgumentAssignment.objects.create(
            spell=self.spell, argument=arg_meta, order=2
        )

        spawn = HydraSpawn.objects.create(
            spellbook=self.book, status=self.status_created
        )
        head = HydraHead.objects.create(
            spawn=spawn, spell=self.spell, status=self.head_status
        )

        result = spell_switches_and_arguments(head_id=head.id)

        expected_flag = f'-id={head.id}'
        self.assertIn(expected_flag, result)

        # Verify Context Dictionary Keys from return (internal check logic)
        # We can't see the dict, but the result proves injection worked.
