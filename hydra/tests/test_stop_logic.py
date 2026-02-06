from django.test import Client, TestCase
from django.urls import reverse

from environments.models import TalosExecutable
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)


class StopLogicTests(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        self.client = Client()

        # Get statuses (Running=3, Stopping=8)
        self.status_running = HydraSpawnStatus.objects.get(id=3)
        self.head_running = HydraHeadStatus.objects.get(id=3)

        # Create minimal graph
        self.book = HydraSpellbook.objects.create(name='Stop Test Protocol')
        self.exe = TalosExecutable.objects.first()
        if not self.exe:
            self.exe = TalosExecutable.objects.create(
                name='TestExe', executable='echo'
            )

        self.spell = HydraSpell.objects.create(
            name='Test Spell', talos_executable=self.exe
        )

        # Create Active Spawn
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status=self.status_running
        )

        self.head = HydraHead.objects.create(
            spawn=self.spawn, spell=self.spell, status=self.head_running
        )

    def test_stop_gracefully_updates_db(self):
        """
        Verify that the view triggers the DB update that the Agent watches for.
        """
        url = (
            reverse(
                'hydra:hydra_spawn_stop_graceful', kwargs={'pk': self.spawn.id}
            )
            + '?silent=true'
        )

        # Simulate button click
        response = self.client.post(url, HTTP_HX_REQUEST='true')

        # Expect 204 No Content (Silent success)
        self.assertEqual(response.status_code, 204)

        # Verify DB Updates
        self.spawn.refresh_from_db()
        self.assertEqual(
            self.spawn.status.id, 8, 'Spawn status should be STOPPING (8)'
        )

        self.head.refresh_from_db()
        self.assertEqual(
            self.head.status.id, 8, 'Head status should be STOPPING (8)'
        )

    def test_stop_halts_graph_execution(self):
        """
        Test that when a spawn is STOPPING, finishing a head does NOT trigger the next node.
        """
        from hydra.hydra import Hydra
        from hydra.models import (
            HydraSpellbookConnectionWire,
            HydraSpellbookNode,
            HydraWireType,
        )

        # 1. Setup Graph: A -> B
        node_a = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell, is_root=True
        )
        node_b = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell
        )

        HydraSpellbookConnectionWire.objects.create(
            spellbook=self.book,
            source=node_a,
            target=node_b,
            type_id=HydraWireType.TYPE_FLOW,
        )

        # 2. Attach existing head to Node A
        self.head.node = node_a
        self.head.save()

        # 3. Trigger Stop
        hydra_ctrl = Hydra(spawn_id=self.spawn.id)
        hydra_ctrl.stop_gracefully()

        self.spawn.refresh_from_db()
        self.assertEqual(self.spawn.status.id, 8)  # STOPPING

        # 4. Simulate Head A finishing
        self.head.refresh_from_db()
        # Note: stop_gracefully sets it to STOPPING.
        # But for the graph to trigger (or try to), the head must finish (SUCCESS or FAILED).
        # We manually transition it to SUCCESS as if the agent finished its job.
        self.head.status_id = 4  # SUCCESS
        self.head.save()

        # 5. Run Dispatcher
        hydra_ctrl.dispatch_next_wave()

        # 6. Verify Node B did not spawn
        heads_for_b = HydraHead.objects.filter(spawn=self.spawn, node=node_b)
        self.assertEqual(
            heads_for_b.count(), 0, 'Node B should not have started'
        )

        # 7. Verify Spawn is now STOPPED
        self.spawn.refresh_from_db()
        self.assertEqual(self.spawn.status.id, 9, 'Spawn should be STOPPED (9)')

    def test_stop_waits_for_all_heads(self):
        """
        Test that Spawn stays STOPPING until ALL heads are done.
        """
        from hydra.hydra import Hydra
        from hydra.models import HydraSpellbookNode

        # 1. Setup two running heads
        node_1 = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell
        )
        node_2 = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell
        )

        # Create additional heads (self.head is already created in setUp)
        head_1 = HydraHead.objects.create(
            spawn=self.spawn,
            node=node_1,
            spell=self.spell,
            status=self.head_running,
        )
        head_2 = HydraHead.objects.create(
            spawn=self.spawn,
            node=node_2,
            spell=self.spell,
            status=self.head_running,
        )

        # Mark initial head as success so it doesn't block
        self.head.status_id = 4
        self.head.save()

        hydra_ctrl = Hydra(spawn_id=self.spawn.id)
        hydra_ctrl.stop_gracefully()

        self.spawn.refresh_from_db()
        self.assertEqual(self.spawn.status.id, 8)  # STOPPING

        # 2. Finish Head 1
        head_1.refresh_from_db()
        head_1.status_id = 4  # SUCCESS
        head_1.save()

        hydra_ctrl.dispatch_next_wave()

        self.spawn.refresh_from_db()
        self.assertEqual(
            self.spawn.status.id,
            8,
            'Should still be STOPPING because head_2 is active',
        )

        # 3. Finish Head 2
        head_2.refresh_from_db()
        head_2.status_id = 4  # SUCCESS
        head_2.save()

        hydra_ctrl.dispatch_next_wave()

        self.spawn.refresh_from_db()
        self.assertEqual(self.spawn.status.id, 9, 'Should be STOPPED now')
