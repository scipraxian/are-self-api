import pytest
from django.test import TestCase

from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
)
from hydra.engine.graph_walker import GraphWalker
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookNode,
)


@pytest.mark.django_db
class GraphWalkerSubGraphTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Setup environment
        env_type = ProjectEnvironmentType.objects.get_or_create(name='UE5')[0]
        env_status = ProjectEnvironmentStatus.objects.get_or_create(
            name='Ready'
        )[0]
        self.env = ProjectEnvironment.objects.create(
            name='Test Env', type=env_type, status=env_status
        )

        # Setup Books & Delegated Node
        self.parent_book = HydraSpellbook.objects.create(name='Parent Book')
        self.child_book = HydraSpellbook.objects.create(name='Child Book')
        self.spell = HydraSpell.objects.create(name='Test Spell')
        self.delegated_node = HydraSpellbookNode.objects.create(
            spellbook=self.parent_book,
            spell=self.spell,
            invoked_spellbook=self.child_book,
        )

        # Setup execution state
        self.spawn_status = HydraSpawnStatus.objects.get_or_create(
            id=1, defaults={'name': 'Created'}
        )[0]
        self.head_status = HydraHeadStatus.objects.get_or_create(
            id=1, defaults={'name': 'Created'}
        )[0]

        # Crucial: Parent Spawn has an environment
        self.parent_spawn = HydraSpawn.objects.create(
            spellbook=self.parent_book,
            environment=self.env,
            status=self.spawn_status,
        )
        self.parent_head = HydraHead.objects.create(
            spawn=self.parent_spawn,
            node=self.delegated_node,
            status=self.head_status,
        )

    def test_subgraph_inherits_environment(self):
        """Verify that delegating to a subgraph passes the environment context down."""
        walker = GraphWalker(spawn_id=self.parent_spawn.id)

        # Trigger the delegation
        walker._spawn_subgraph(self.parent_head)

        # Retrieve the newly created child spawn
        child_spawn = HydraSpawn.objects.get(parent_head=self.parent_head)

        # Assert inheritance
        self.assertIsNotNone(
            child_spawn.environment, 'Child spawn lost the environment context!'
        )
        self.assertEqual(
            child_spawn.environment.id,
            self.env.id,
            'Child spawn inherited the WRONG environment!',
        )
