from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase

from environments.models import TalosExecutable
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)
from hydra.spells.spell_casters.generic_spell_caster import GenericSpellCaster

MODULE_PATH = 'hydra.spells.spell_casters.generic_spell_caster'


class GenericSpellcasterTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Setup Data Hierarchy using Fixtures
        self.spellbook = HydraSpellbook.objects.first()
        from environments.models import ProjectEnvironment

        self.proj_env = ProjectEnvironment.objects.first()

        self.spawn = HydraSpawn.objects.create(
            status_id=HydraSpawnStatus.CREATED,
            spellbook=self.spellbook,
            environment=self.proj_env,
        )

        # 2. Use a standard executable (PYTHON) for default state
        self.python_exe = TalosExecutable.objects.get(id=TalosExecutable.PYTHON)

        self.spell = HydraSpell.objects.create(
            name='Unit Test Spell',
            talos_executable=self.python_exe,
        )

        self.head = HydraHead.objects.create(spell=self.spell,
                                             spawn=self.spawn,
                                             status_id=HydraHeadStatus.CREATED)

    def test_generic_spellcaster_instantiates(self):
        """Asserts that the GenericSpellCaster can be instantiated."""
        try:
            GenericSpellCaster(self.head.id)
        except Exception as e:
            self.fail(f'Failed to instantiate GenericSpellCaster: {e}')

    async def _mock_executable_router(self, caster):
        # Helper to simulate calling the router since it is async
        await caster._executable_router()

    def test_generic_spellcaster_executable_router(self):
        """Assert executable router selects the correct executable logic."""
        caster = GenericSpellCaster(self.head.id)
        caster.head = self.head
        caster.spell = self.head.spell

        # Mock the methods called by router
        caster._execute_local_python = AsyncMock()
        caster._execute_unified_pipeline = AsyncMock()

        # Helper to run the async method synchronously for testing
        import asyncio

        # Case 1: Standard Executable (PYTHON) -> Unified Pipeline
        caster.spell.talos_executable = self.python_exe

        # We need to run the async method
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(caster._executable_router())

        caster._execute_unified_pipeline.assert_called_once()
        caster._execute_local_python.assert_not_called()

        # Reset Mocks
        caster._execute_unified_pipeline.reset_mock()
        caster._execute_local_python.reset_mock()

        # Case 2: Internal Handler -> Local Python
        internal_exe = TalosExecutable.objects.get(
            id=TalosExecutable.VERSION_HANDLER)
        caster.spell.talos_executable = internal_exe

        loop.run_until_complete(caster._executable_router())

        caster._execute_local_python.assert_called_once()
        caster._execute_unified_pipeline.assert_not_called()
        loop.close()
