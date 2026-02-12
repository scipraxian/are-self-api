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
        'talos_frontal/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Setup Infrastructure
        self.env_type = ProjectEnvironmentType.objects.create(name='TestType')
        self.env_status = ProjectEnvironmentStatus.objects.create(name='Active')
        self.env = ProjectEnvironment.objects.create(
            name='Base Env',
            type=self.env_type,
            status=self.env_status,
            selected=True,
        )

        self.exe = TalosExecutable.objects.create(
            name='TestExe', executable='echo'
        )
        self.spell = HydraSpell.objects.create(
            name='Test Spell', talos_executable=self.exe
        )
        self.book = HydraSpellbook.objects.create(name='Test Book')

        # Statuses
        self.spawn_status = HydraSpawnStatus.objects.get(name='Created')
        self.head_status = HydraHeadStatus.objects.get(name='Created')

        # The Variable Key we are testing
        self.VAR_KEY = 'prompt'

    def test_hierarchy_resolution(self):
        """
        Verifies the precedence order:
        1. Environment (Base)
        2. Spell Default (Tier 1)
        3. Node Override (Tier 2)
        4. Spawn Injection (Tier 3)
        """
        # --- LEVEL 0: Environment ---
        key_obj = ProjectEnvironmentContextKey.objects.create(name=self.VAR_KEY)
        ContextVariable.objects.create(
            environment=self.env, key=key_obj, value='LEVEL_0_ENV'
        )

        # --- LEVEL 1: Spell Default ---
        HydraSpellContext.objects.create(
            spell=self.spell, key=self.VAR_KEY, value='LEVEL_1_SPELL'
        )

        # --- LEVEL 2: Node Override ---
        node = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell
        )
        HydraSpellBookNodeContext.objects.create(
            node=node, key=self.VAR_KEY, value='LEVEL_2_NODE'
        )

        # --- LEVEL 3: Spawn Injection ---
        spawn_context = {self.VAR_KEY: 'LEVEL_3_SPAWN'}
        spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            status=self.spawn_status,
            environment=self.env,
            context_data=json.dumps(spawn_context),
        )

        head = HydraHead.objects.create(
            spawn=spawn, node=node, spell=self.spell, status=self.head_status
        )

        # ACT 1: Full Stack -> Spawn wins
        ctx = resolve_environment_context(head_id=head.id)
        self.assertEqual(
            ctx[self.VAR_KEY],
            'LEVEL_3_SPAWN',
            'Tier 3 (Spawn) failed to override lower layers.',
        )

        # ACT 2: Remove Spawn Context -> Node wins
        spawn.context_data = '{}'
        spawn.save()
        ctx = resolve_environment_context(head_id=head.id)
        self.assertEqual(
            ctx[self.VAR_KEY],
            'LEVEL_2_NODE',
            'Tier 2 (Node) failed to override Spell/Env.',
        )

        # ACT 3: Remove Node Context -> Spell wins
        HydraSpellBookNodeContext.objects.all().delete()
        ctx = resolve_environment_context(head_id=head.id)
        self.assertEqual(
            ctx[self.VAR_KEY],
            'LEVEL_1_SPELL',
            'Tier 1 (Spell) failed to override Environment.',
        )

        # ACT 4: Remove Spell Context -> Environment wins
        HydraSpellContext.objects.all().delete()
        ctx = resolve_environment_context(head_id=head.id)
        self.assertEqual(
            ctx[self.VAR_KEY],
            'LEVEL_0_ENV',
            'Base Environment failed to provide fallback value.',
        )
