import pytest
from django.test import TestCase

from environments.models import (
    ContextVariable,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
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
from hydra.utils import get_active_environment, resolve_environment_context


@pytest.mark.django_db
class CommandGenerationTest(TestCase):
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
        key_root, _ = ProjectEnvironmentContextKey.objects.get_or_create(
            name='project_root'
        )

        # Fix: Create vars using correct keys
        ContextVariable.objects.create(
            environment=self.env_default,
            key=key_root,
            value='C:/Default',
        )
        ContextVariable.objects.create(
            environment=self.env_spawn,
            key=key_root,
            value='C:/Spawn',
        )
        ContextVariable.objects.create(
            environment=self.env_node,
            key=key_root,
            value='C:/Node',
        )

        # 4. Create Argument
        self.arg = TalosExecutableArgument.objects.create(
            name='Project Flag', argument='-project={{ project_root }}'
        )
        HydraSpellArgumentAssignment.objects.create(
            spell=self.spell, argument=self.arg, order=1
        )

    def _get_command(self, head=None, environment=None, extra_context=None):
        if head:
            env = get_active_environment(head)
            ctx = resolve_environment_context(head_id=head.id)
            return self.spell.get_full_command(
                environment=env, extra_context=ctx
            )

        return self.spell.get_full_command(
            environment=environment, extra_context=extra_context
        )

    def test_legacy_mode(self):
        """Verifies calling with just environment works."""
        # result = self.spell.get_full_command(environment=None)
        # However, variable 'project_root' will be empty
        result = self._get_command(environment=None)
        self.assertIn('-project=', result[1])  # result[0] is executable

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

        result = self._get_command(head=head)
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

        result = self._get_command(head=head)
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

        result = self._get_command(head=head)
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

        result = self._get_command(head=head)

        expected_flag = f'-id={head.id}'
        self.assertIn(expected_flag, result)
