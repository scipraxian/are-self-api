from django.test import TestCase

from environments.models import ProjectEnvironment
from hydra.engine.graph_walker import GraphWalker
from hydra.hydra import Hydra
from hydra.models import (
    HydraDistributionModeID,
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraSpellBookNodeContext,
    HydraWireType,
)
from talos_agent.models import TalosAgentRegistry, TalosAgentStatus


class BlackboardThroughputTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def test_horizontal_sibling_handoff(self):
        """Prove Working Memory passes flawlessly across standard Flow wires."""
        env = ProjectEnvironment.objects.get(selected=True)
        spell = HydraSpell.objects.get(pk=1)  # Begin Play
        book = HydraSpellbook.objects.create(
            name='Horizontal Test', environment=env
        )

        # Setup linear graph: Node A -> Node B
        node_a = HydraSpellbookNode.objects.create(spellbook=book, spell=spell)
        node_b = HydraSpellbookNode.objects.create(spellbook=book, spell=spell)

        HydraSpellbookConnectionWire.objects.create(
            spellbook=book,
            source=node_a,
            target=node_b,
            type_id=HydraWireType.TYPE_FLOW,
        )

        spawn = HydraSpawn.objects.create(
            spellbook=book, status_id=HydraSpawnStatus.RUNNING, environment=env
        )

        # Inject memory into the finished Head A
        head_a = HydraHead.objects.create(
            spawn=spawn,
            node=node_a,
            spell=spell,
            status_id=HydraHeadStatus.SUCCESS,
            blackboard={'detected_error': 'Syntax Error line 42'},
        )

        # Trigger the engine to walk the wire
        hydra_engine = Hydra(spawn_id=spawn.id)
        hydra_engine._process_graph_triggers(head_a)

        # Assert Node B woke up with Node A's exact memory
        head_b = HydraHead.objects.get(provenance=head_a)
        self.assertEqual(
            head_b.blackboard.get('detected_error'), 'Syntax Error line 42'
        )

    def test_vertical_subgraph_handoff(self):
        """Prove Working Memory drops into subgraphs and absorbs Subgraph Node Overrides."""
        env = ProjectEnvironment.objects.get(selected=True)
        spell = HydraSpell.objects.get(pk=1)

        parent_book = HydraSpellbook.objects.create(
            name='Parent Graph', environment=env
        )
        child_book = HydraSpellbook.objects.create(
            name='Child Graph', environment=env
        )

        # The Subgraph Node
        delegator_node = HydraSpellbookNode.objects.create(
            spellbook=parent_book, spell=spell, invoked_spellbook=child_book
        )

        # The specific override argument injected into the Inspector UI
        HydraSpellBookNodeContext.objects.create(
            node=delegator_node, key='target_branch', value='release'
        )

        # The entry point of the Subgraph
        child_root = HydraSpellbookNode.objects.create(
            spellbook=child_book, spell=spell, is_root=True
        )

        parent_spawn = HydraSpawn.objects.create(
            spellbook=parent_book,
            status_id=HydraSpawnStatus.RUNNING,
            environment=env,
        )

        # Parent Head has existing historic memory
        parent_head = HydraHead.objects.create(
            spawn=parent_spawn,
            node=delegator_node,
            spell=spell,
            status_id=HydraHeadStatus.RUNNING,
            blackboard={'global_session_id': 'ABC-123'},
        )

        # Trigger the delegation boundary crossing
        walker = GraphWalker(spawn_id=parent_spawn.id)
        walker._spawn_subgraph(parent_head)

        child_spawn = HydraSpawn.objects.get(parent_head=parent_head)

        # Simulate Engine starting the Child Spawn
        child_engine = Hydra(spawn_id=child_spawn.id)
        child_engine.dispatch_next_wave()

        # Fetch the newly born Root Head inside the Child Spawn
        child_head = HydraHead.objects.get(spawn=child_spawn, node=child_root)

        # Assert memory retention AND UI override injection
        self.assertEqual(
            child_head.blackboard.get('global_session_id'), 'ABC-123'
        )
        self.assertEqual(child_head.blackboard.get('target_branch'), 'release')

    def test_fleet_broadcast_handoff(self):
        """Prove Working Memory clones flawlessly across parallel fleet distribution."""
        env = ProjectEnvironment.objects.get(selected=True)
        spell = HydraSpell.objects.get(pk=1)
        book = HydraSpellbook.objects.create(
            name='Fleet Graph', environment=env
        )

        node = HydraSpellbookNode.objects.create(
            spellbook=book,
            spell=spell,
            distribution_mode_id=HydraDistributionModeID.ALL_ONLINE_AGENTS,
        )

        spawn = HydraSpawn.objects.create(
            spellbook=book, status_id=HydraSpawnStatus.RUNNING, environment=env
        )

        online_agents_count = TalosAgentRegistry.objects.filter(
            status_id=TalosAgentStatus.ONLINE
        ).count()
        self.assertTrue(
            online_agents_count > 0,
            'Fixture requires online agents for this test.',
        )

        seed_head = HydraHead.objects.create(
            spawn=spawn,
            node=node,
            spell=spell,
            status_id=HydraHeadStatus.CREATED,
            blackboard={'fleet_directive': 'Execute Order 66'},
        )

        # Trigger Broadcast
        engine = Hydra(spawn_id=spawn.id)
        engine._dispatch_fleet_wave(seed_head)

        # Assert Clones
        clones = HydraHead.objects.filter(spawn=spawn, node=node).exclude(
            id=seed_head.id
        )
        self.assertEqual(clones.count(), online_agents_count)

        for clone in clones:
            self.assertEqual(
                clone.blackboard.get('fleet_directive'), 'Execute Order 66'
            )
