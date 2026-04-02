from unittest.mock import AsyncMock, MagicMock, patch

from common.tests.common_test_case import CommonFixturesAPITestCase

from environments.models import Executable
from central_nervous_system.models import (
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
    Effector,
    NeuralPathway,
)
from central_nervous_system.effectors.effector_casters.neuromuscular_junction import NeuroMuscularJunction

MODULE_PATH = 'central_nervous_system.effectors.effector_casters.neuromuscular_junction'


class NeuroMuscularJunctionTest(CommonFixturesAPITestCase):

    def setUp(self):
        # 1. Setup Data Hierarchy using Fixtures
        self.pathway = NeuralPathway.objects.first()
        from environments.models import ProjectEnvironment

        self.proj_env = ProjectEnvironment.objects.first()

        self.spike_train = SpikeTrain.objects.create(
            status_id=SpikeTrainStatus.CREATED,
            pathway=self.pathway,
            environment=self.proj_env,
        )

        # 2. Use a standard executable (PYTHON) for default state
        self.python_exe = Executable.objects.get(id=Executable.PYTHON)

        self.effector = Effector.objects.create(
            name='Unit Test Spell',
            talos_executable=self.python_exe,
        )

        self.spike = Spike.objects.create(effector=self.effector,
                                          spike_train=self.spike_train,
                                          status_id=SpikeStatus.CREATED)

    def test_generic_spellcaster_instantiates(self):
        """Asserts that the NeuroMuscularJunction can be instantiated."""
        try:
            NeuroMuscularJunction(self.spike.id)
        except Exception as e:
            self.fail(f'Failed to instantiate NeuroMuscularJunction: {e}')

    async def _mock_executable_router(self, caster):
        # Helper to simulate calling the router since it is async
        await caster._executable_router()

    def test_generic_spellcaster_executable_router(self):
        """Assert executable router selects the correct executable logic."""
        caster = NeuroMuscularJunction(self.spike.id)
        caster.spike = self.spike
        caster.effector = self.spike.effector

        # Mock the methods called by router
        caster._execute_local_python = AsyncMock()
        caster._execute_unified_pipeline = AsyncMock()

        # Helper to run the async method synchronously for testing
        import asyncio

        # Case 1: Standard Executable (PYTHON) -> Unified Pipeline
        caster.effector.talos_executable = self.python_exe

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
        internal_exe = Executable.objects.get(
            id=Executable.VERSION_HANDLER)
        caster.effector.talos_executable = internal_exe

        loop.run_until_complete(caster._executable_router())

        caster._execute_local_python.assert_called_once()
        caster._execute_unified_pipeline.assert_not_called()
        loop.close()
