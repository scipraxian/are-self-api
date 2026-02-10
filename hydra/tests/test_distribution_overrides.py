# [file: hydra/tests/test_distribution_overrides.py]
from unittest.mock import patch

from django.test import TestCase

from hydra.hydra import Hydra
from hydra.models import (
    HydraDistributionModeID,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookNode,
)


class DistributionOverrideTest(TestCase):
    """Verifies the hierarchy: Node Override > Spell Default."""

    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        self.book = HydraSpellbook.objects.create(name='Override Test')
        self.spell = HydraSpell.objects.get(pk=1)

        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.CREATED
        )

    @patch('hydra.hydra.Hydra._dispatch_fleet_wave')
    @patch('hydra.hydra.Hydra._prepare_and_dispatch')
    def test_priority_node_override(self, mock_local, mock_fleet):
        """Verify Node override (Fleet) beats Spell default (Local)."""
        node = HydraSpellbookNode.objects.create(
            spellbook=self.book,
            spell=self.spell,
            is_root=True,
            distribution_mode_id=HydraDistributionModeID.ALL_ONLINE_AGENTS,
        )

        controller = Hydra(spawn_id=self.spawn.id)
        controller.start()

        # Should NOT use the spell's LOCAL_SERVER [cite: 400]
        mock_local.assert_not_called()
        # Should use the node's ALL_ONLINE_AGENTS
        mock_fleet.assert_called_once()

    @patch('hydra.hydra.Hydra._prepare_and_dispatch')
    def test_fallback_to_spell_default(self, mock_local):
        """Verify fallback to Spell default when Node override is NULL."""
        node = HydraSpellbookNode.objects.create(
            spellbook=self.book,
            spell=self.spell,
            is_root=True,
            distribution_mode=None,  # Explicit fallback
        )

        controller = Hydra(spawn_id=self.spawn.id)
        controller.start()

        # Should use the spell's default (LOCAL_SERVER)
        mock_local.assert_called_once()

    @patch('hydra.hydra.Hydra._dispatch_first_responder')
    def test_different_overrides_on_same_spell(self, mock_first_responder):
        """Verify two different nodes using the same spell can have different modes."""
        node_a = HydraSpellbookNode.objects.create(
            spellbook=self.book,
            spell=self.spell,
            is_root=True,
            distribution_mode_id=HydraDistributionModeID.ONE_AVAILABLE_AGENT,
        )

        controller = Hydra(spawn_id=self.spawn.id)
        controller.start()

        mock_first_responder.assert_called_once()
