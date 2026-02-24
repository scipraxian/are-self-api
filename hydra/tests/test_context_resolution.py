import json

from django.test import TestCase

from environments.models import (
    ContextVariable,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
    TalosExecutable,
)
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookNode,
    HydraSpellBookNodeContext,
    HydraSpellContext,
)
from hydra.utils import resolve_environment_context


class ContextResolutionTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
        'frontal_lobe/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Base Environment Infrastructure
        self.env_type = ProjectEnvironmentType.objects.create(name='TestType')
        self.env_status = ProjectEnvironmentStatus.objects.create(name='Active')
        self.env = ProjectEnvironment.objects.create(
            name='Base Env',
            type=self.env_type,
            status=self.env_status,
            selected=True,
        )

        # 2. Base Execution Infrastructure
        self.exe = TalosExecutable.objects.create(
            name='TestExe', executable='echo'
        )
        self.spell = HydraSpell.objects.create(
            name='Test Spell', talos_executable=self.exe
        )
        self.book = HydraSpellbook.objects.create(name='Test Book')
        self.node = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell, environment=self.env
        )

        # 3. Base Run Infrastructure
        self.spawn_status = HydraSpawnStatus.objects.get(
            id=HydraSpawnStatus.CREATED
        )
        self.head_status = HydraHeadStatus.objects.get(
            id=HydraHeadStatus.CREATED
        )
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            status_id=HydraSpawnStatus.CREATED,
            environment=self.env,
        )

        # 4. Standardized Test Keys
        self.KEY_PROMPT = 'prompt'
        self.KEY_TARGET = 'target_email'

    def _create_env_variable(self, key_name: str, value: str):
        """Helper to properly create relational environment variables."""
        key_obj, _ = ProjectEnvironmentContextKey.objects.get_or_create(
            name=key_name
        )
        ContextVariable.objects.create(
            environment=self.env, key=key_obj, value=value
        )

    def test_pure_environment_extraction(self):
        """
        Prove that a pure environment variable is correctly extracted
        when no other overrides exist.
        """
        self._create_env_variable(self.KEY_PROMPT, 'ENV_PROMPT')

        head = HydraHead.objects.create(
            spawn=self.spawn,
            node=self.node,
            spell=self.spell,
            status=self.head_status,
        )

        ctx = resolve_environment_context(head_id=head.id)

        self.assertIn(self.KEY_PROMPT, ctx)
        self.assertEqual(ctx[self.KEY_PROMPT], 'ENV_PROMPT')

    def test_blackboard_overrides_environment(self):
        """
        Prove that the dynamic Working Memory (Blackboard) correctly overwrites
        a static Global Environment variable.
        """
        # 1. Set the baseline in the Environment
        self._create_env_variable(self.KEY_TARGET, 'team@studio.com')

        # 2. The AI decides to change it mid-run via the Blackboard
        head = HydraHead.objects.create(
            spawn=self.spawn,
            node=self.node,
            spell=self.spell,
            status=self.head_status,
            blackboard={self.KEY_TARGET: 'ceo@studio.com'},
        )

        # 3. Resolve and assert the AI's memory wins
        ctx = resolve_environment_context(head_id=head.id)
        self.assertEqual(
            ctx[self.KEY_TARGET],
            'ceo@studio.com',
            'Blackboard failed to override the Global Environment.',
        )

    def test_strict_hierarchy_precedence(self):
        """
        The Crucible: Prove the exact 4-tier hierarchy of variable precedence.
        Node Override > Spell Default > Blackboard > Global Environment
        """
        # --- LEVEL 1: Global Environment ---
        self._create_env_variable(self.KEY_PROMPT, 'LEVEL_1_ENV')

        head = HydraHead.objects.create(
            spawn=self.spawn,
            node=self.node,
            spell=self.spell,
            status=self.head_status,
            blackboard={},
        )

        # Assert Baseline
        ctx = resolve_environment_context(head_id=head.id)
        self.assertEqual(ctx[self.KEY_PROMPT], 'LEVEL_1_ENV')

        # --- LEVEL 2: Blackboard ---
        head.blackboard = {self.KEY_PROMPT: 'LEVEL_2_BLACKBOARD'}
        head.save()

        # Assert Blackboard wins
        ctx = resolve_environment_context(head_id=head.id)
        self.assertEqual(ctx[self.KEY_PROMPT], 'LEVEL_2_BLACKBOARD')

        # --- LEVEL 3: Spell Default ---
        HydraSpellContext.objects.create(
            spell=self.spell, key=self.KEY_PROMPT, value='LEVEL_3_SPELL'
        )

        # Assert Spell Default wins
        ctx = resolve_environment_context(head_id=head.id)
        self.assertEqual(ctx[self.KEY_PROMPT], 'LEVEL_3_SPELL')

        # --- LEVEL 4: Node Override ---
        HydraSpellBookNodeContext.objects.create(
            node=self.node, key=self.KEY_PROMPT, value='LEVEL_4_NODE'
        )

        # Assert Node Override is the Absolute King
        ctx = resolve_environment_context(head_id=head.id)
        self.assertEqual(ctx[self.KEY_PROMPT], 'LEVEL_4_NODE')

    def test_blackboard_preserves_unrelated_environment_keys(self):
        """
        Prove that merging the Blackboard doesn't accidentally erase
        unrelated Environment variables.
        """
        self._create_env_variable('engine_path', 'C:/UE5')
        self._create_env_variable('project_name', 'TalosGame')

        head = HydraHead.objects.create(
            spawn=self.spawn,
            node=self.node,
            spell=self.spell,
            status=self.head_status,
            blackboard={'ai_summary': 'Clean build.'},
        )

        ctx = resolve_environment_context(head_id=head.id)

        # Both the Environment and the Blackboard should co-exist
        self.assertEqual(ctx['engine_path'], 'C:/UE5')
        self.assertEqual(ctx['project_name'], 'TalosGame')
        self.assertEqual(ctx['ai_summary'], 'Clean build.')
