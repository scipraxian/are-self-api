import json
import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from environments.models import (
    ContextVariable,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
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
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraSpellBookNodeContext,
    HydraWireType,
)


class GraphAPITests(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Setup Auth
        self.user = User.objects.create_superuser(
            'testadmin', 'admin@talos.dev', 'password'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # 2. Base Models
        self.book = HydraSpellbook.objects.create(name='Graph Test Protocol')
        self.spell = HydraSpell.objects.create(
            name='Compile Project',
            talos_executable=TalosExecutable.objects.first(),
        )
        self.begin_play = HydraSpell.objects.get(id=HydraSpell.BEGIN_PLAY)

        # 3. Graph Setup
        self.root_node = HydraSpellbookNode.objects.create(
            spellbook=self.book,
            spell=self.begin_play,
            is_root=True,
            ui_json='{"x": 100, "y": 100}',
        )
        self.task_node = HydraSpellbookNode.objects.create(
            spellbook=self.book,
            spell=self.spell,
            ui_json='{"x": 300, "y": 100}',
        )
        self.wire_type_flow = HydraWireType.objects.get(
            id=HydraWireType.TYPE_FLOW
        )

        HydraSpellbookConnectionWire.objects.create(
            spellbook=self.book,
            source=self.root_node,
            target=self.task_node,
            type=self.wire_type_flow,
        )

    def test_get_graph_layout(self):
        """Verifies the layout endpoint returns formatted nodes and wires for the UI Canvas."""
        url = f'/api/v1/spellbooks/{self.book.id}/layout/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('nodes', response.data)
        self.assertIn('connections', response.data)

        # Verify Nodes shape
        nodes = response.data['nodes']
        self.assertEqual(len(nodes), 2)
        root_data = next(n for n in nodes if n['is_root'])
        self.assertEqual(root_data['x'], 100)
        self.assertEqual(root_data['title'], 'Begin Play')

        # Verify Wires shape
        wires = response.data['connections']
        self.assertEqual(len(wires), 1)
        self.assertEqual(wires[0]['from_node_id'], self.root_node.id)
        self.assertEqual(wires[0]['status_id'], 'flow')

    def test_get_library(self):
        """Verifies the sidebar library endpoint returns Spells and Subgraphs."""
        subgraph = HydraSpellbook.objects.create(name='Inner Graph')

        url = f'/api/v1/spellbooks/{self.book.id}/library/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        library = response.data['library']

        # Ensure it contains spells
        spells = [item for item in library if item.get('category') == 'Spells']
        self.assertTrue(len(spells) > 0)

        # Ensure it contains subgraphs
        graphs = [
            item for item in library if item.get('category') == 'Sub-Graphs'
        ]
        # FIX: The fixture loads ~22 books, plus the one we just made.
        self.assertTrue(len(graphs) >= 1)

        # Find the specific one we just made
        inner_graph_data = next(
            (g for g in graphs if g['name'] == 'Inner Graph'), None
        )
        self.assertIsNotNone(
            inner_graph_data, 'Newly created subgraph missing from library.'
        )
        self.assertTrue(inner_graph_data['is_book'])

    def test_create_node_handles_json(self):
        """Verifies we can POST to create a node, and DRF handles the JSON stringification."""
        url = '/api/v1/nodes/'
        payload = {
            'spellbook': self.book.id,
            'spell': self.spell.id,
            'ui_json': {'x': 450, 'y': 250},  # Raw dict
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        node_id = response.data['id']
        node = HydraSpellbookNode.objects.get(id=node_id)

        # DB should store it as string
        self.assertIsInstance(node.ui_json, str)
        # API should return it as Dict
        self.assertIsInstance(response.data['ui_json'], dict)
        self.assertEqual(response.data['ui_json']['x'], 450)

    def test_node_deletion_protection(self):
        """Verifies you cannot delete the BeginPlay root node."""
        url = f'/api/v1/nodes/{self.root_node.id}/'
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot delete', str(response.data))

        # Ensure standard node CAN be deleted
        url_task = f'/api/v1/nodes/{self.task_node.id}/'
        response_task = self.client.delete(url_task)
        self.assertEqual(response_task.status_code, status.HTTP_204_NO_CONTENT)

    def test_live_status_polling(self):
        """Verifies the fast-polling endpoint returns accurate node states."""
        spawn_status = HydraSpawnStatus.objects.get(id=3)  # Running
        head_status = HydraHeadStatus.objects.get(id=3)  # Running

        spawn = HydraSpawn.objects.create(
            spellbook=self.book, status=spawn_status
        )
        head = HydraHead.objects.create(
            spawn=spawn,
            spell=self.spell,
            node=self.task_node,
            status=head_status,
        )

        url = f'/api/v1/spawns/{spawn.id}/live_status/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_active'])
        self.assertEqual(response.data['status_label'], 'Running')

        nodes_map = response.data['nodes']
        # BeginPlay is auto-injected as success (id 4)
        self.assertEqual(nodes_map[str(self.root_node.id)]['status_id'], 4)
        # Task node reflects actual Head status
        self.assertEqual(nodes_map[str(self.task_node.id)]['status_id'], 3)
        self.assertEqual(
            nodes_map[str(self.task_node.id)]['head_id'], str(head.id)
        )

    def test_inspector_details(self):
        """Verifies the Smart Context Matrix endpoint generates properly."""
        env = ProjectEnvironment.objects.first()
        self.book.environment = env
        self.book.save()

        # [FIX]: The Smart Matrix ONLY shows variables that are actively used by the spell.
        # We must add an argument containing {{ project_name }} so the regex extractor finds it.
        arg = TalosExecutableArgument.objects.create(
            name='Proj Arg', argument='-p={{ project_name }}'
        )
        HydraSpellArgumentAssignment.objects.create(
            spell=self.spell, argument=arg, order=1
        )

        # 1. Global Var
        key, _ = ProjectEnvironmentContextKey.objects.get_or_create(
            name='project_name'
        )
        ContextVariable.objects.create(
            environment=env, key=key, value='Global_HSH'
        )

        # 2. Node Override
        HydraSpellBookNodeContext.objects.create(
            node=self.task_node, key='project_name', value='Override_HSH'
        )

        url = f'/api/v1/nodes/{self.task_node.id}/inspector_details/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        matrix = response.data['context_matrix']

        # Verify the matrix caught the variable and recognized it as an override
        var_entry = next(
            (m for m in matrix if m['key'] == 'project_name'), None
        )
        self.assertIsNotNone(var_entry)
        self.assertEqual(var_entry['source'], 'override')
        self.assertEqual(var_entry['value'], 'Override_HSH')
