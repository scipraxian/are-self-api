import uuid
from datetime import timedelta

import pytest
from django.test import TestCase
from django.utils import timezone

from environments.models import TalosExecutable
from hydra.models import (
    HydraHead,
    HydraSpawn,
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookNode,
    HydraWireType,
)
from hydra.serializers import (
    HydraHeadSerializer,
    HydraNodeTelemetrySerializer,
    HydraSpawnCreateSerializer,
    HydraSpellbookConnectionWireSerializer,
    HydraSpellbookNodeSerializer,
)


@pytest.mark.django_db
class HydraSerializersTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Basics
        self.book = HydraSpellbook.objects.create(name='Book A')
        self.book_b = HydraSpellbook.objects.create(name='Book B')

        self.spell = HydraSpell.objects.create(
            name='Test Spell',
            talos_executable=TalosExecutable.objects.create(
                name='Exe', executable='cmd.exe'
            ),
        )

        # Nodes
        self.node_a1 = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell
        )
        self.node_a2 = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell
        )
        self.node_b1 = HydraSpellbookNode.objects.create(
            spellbook=self.book_b, spell=self.spell
        )

        # Wire Type
        self.wire_flow = HydraWireType.objects.get(id=1, name='Flow')

    def test_spawn_create_validation(self):
        """Verify Launch Request validation."""
        # Valid
        valid_data = {'spellbook_id': self.book.id}
        serializer = HydraSpawnCreateSerializer(data=valid_data)
        self.assertTrue(serializer.is_valid())

        # Invalid (Bad ID)
        invalid_data = {'spellbook_id': uuid.uuid4()}
        serializer = HydraSpawnCreateSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('not found', str(serializer.errors['spellbook_id']))

    def test_wire_integrity_validation(self):
        """Ensure wires cannot connect nodes from different spellbooks."""
        # 1. Valid Connection (Same Book)
        valid_data = {
            'spellbook': self.book.id,
            'source': self.node_a1.id,
            'target': self.node_a2.id,
            'type': self.wire_flow.id,
        }
        serializer = HydraSpellbookConnectionWireSerializer(data=valid_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        # 2. Invalid Connection (Cross Book)
        invalid_data = {
            'spellbook': self.book.id,
            'source': self.node_a1.id,
            'target': self.node_b1.id,  # Belongs to Book B
            'type': self.wire_flow.id,
        }
        serializer = HydraSpellbookConnectionWireSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('Target node does not belong', str(serializer.errors))

    def test_node_ui_json_handling(self):
        """Verify ui_json handles Dict input and stores as String."""
        # 1. Write (Dict -> String)
        payload = {
            'spellbook': self.book.id,
            'spell': self.spell.id,
            'ui_json': {'x': 500, 'y': 200},  # Raw Dict
            'is_root': False,
        }
        serializer = HydraSpellbookNodeSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        node = serializer.save()

        # Verify DB Storage
        node.refresh_from_db()
        self.assertIsInstance(node.ui_json, str)
        self.assertIn('"x": 500', node.ui_json)

        # 2. Read (String -> Dict)
        read_serializer = HydraSpellbookNodeSerializer(node)
        self.assertIsInstance(read_serializer.data['ui_json'], dict)
        self.assertEqual(read_serializer.data['ui_json']['x'], 500)

    def test_head_serializer_excludes_logs(self):
        """Verify list-view serializer prevents heavy log dumps."""
        head = HydraHead.objects.create(
            spawn=HydraSpawn.objects.create(spellbook=self.book, status_id=1),
            spell=self.spell,
            status_id=1,
            spell_log='MASSIVE LOG DATA ' * 1000,
            execution_log='SYSTEM DATA ' * 1000,
        )

        data = HydraHeadSerializer(head).data
        self.assertNotIn('spell_log', data)
        self.assertNotIn('execution_log', data)
        self.assertIn('id', data)

    def test_telemetry_command_resolution(self):
        """Verify command string is reconstructed via context resolution."""
        # Setup context
        # This implicitly tests get_active_environment and resolve_environment_context logic
        # embedded in the serializer
        head = HydraHead.objects.create(
            spawn=HydraSpawn.objects.create(spellbook=self.book, status_id=1),
            spell=self.spell,
            status_id=1,
        )

        data = HydraNodeTelemetrySerializer(head).data
        # Should contain executable name "cmd.exe"
        self.assertIn('cmd.exe', data['command'])
