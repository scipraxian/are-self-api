from unittest.mock import patch

from central_nervous_system.central_nervous_system import CNS
from central_nervous_system.models import (
    Axon,
    AxonType,
    Effector,
    NeuralPathway,
    Neuron,
    Spike,
    SpikeStatus,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
    Executable,
)


class CNSGraphRoutingTest(CommonFixturesAPITestCase):

    def setUp(self):
        # Environment
        env_type = ProjectEnvironmentType.objects.get_or_create(name='UE5')[0]
        env_status = ProjectEnvironmentStatus.objects.get_or_create(
            name='Ready')[0]
        self.env = ProjectEnvironment.objects.create(name='Test Env',
                                                     type=env_type,
                                                     status=env_status)
        self.env.selected = True
        self.env.save()

        # Effector & Nodes
        self.exe = Executable.objects.create(name='TestExe',
                                                  executable='cmd.exe')
        self.effector = Effector.objects.create(name='TestSpell',
                                                executable=self.exe)
        self.book = NeuralPathway.objects.create(name='Test Book')
        self.neuron1 = Neuron.objects.create(pathway=self.book,
                                             effector=self.effector,
                                             environment=self.env,
                                             is_root=True)
        self.neuron2 = Neuron.objects.create(pathway=self.book,
                                             effector=self.effector,
                                             environment=self.env,
                                             is_root=False)

        axon_type_success = AxonType.objects.get(id=AxonType.TYPE_SUCCESS)
        self.axon = Axon.objects.create(pathway=self.book,
                                        source=self.neuron1,
                                        target=self.neuron2,
                                        type=axon_type_success)

    @patch('central_nervous_system.central_nervous_system.fire_spike.delay')
    def test_creates_head_from_node_on_success(self, mock_fire_spike_delay):
        """Verify CNS._process_graph_triggers successfully traverses wires to spawn child Spikes."""

        cns = CNS(pathway_id=self.book.id)

        # 1. Dispatch Root
        with self.captureOnCommitCallbacks(execute=True):
            cns.dispatch_next_wave()

        # Verify the root spike is spawned and pending
        spikes = Spike.objects.filter(spike_train=cns.spike_train)
        self.assertEqual(spikes.count(), 1)

        root_spike = spikes.first()
        self.assertEqual(root_spike.neuron, self.neuron1)
        self.assertEqual(root_spike.status_id, SpikeStatus.PENDING)

        # 2. Simulate Success
        root_spike.status_id = SpikeStatus.SUCCESS
        root_spike.save()

        # 3. Process Graph Triggers directly to explicitly test this edge case
        with self.captureOnCommitCallbacks(execute=True):
            cns._process_graph_triggers(root_spike)

        # Verify the second spike was generated via the Axon
        spikes_now = Spike.objects.filter(
            spike_train=cns.spike_train).order_by('created')
        self.assertEqual(spikes_now.count(), 2)

        child_spike = spikes_now.last()
        self.assertEqual(child_spike.neuron, self.neuron2)
        self.assertEqual(child_spike.provenance, root_spike)
        self.assertEqual(child_spike.status_id, SpikeStatus.PENDING)

        # Assert task enqueued
        mock_fire_spike_delay.assert_called_with(child_spike.id)

    @patch('central_nervous_system.central_nervous_system.fire_spike.delay')
    def test_logic_retry_failure_does_not_fire_flow_axon(
        self, mock_fire_spike_delay
    ):
        """Assert a failed LOGIC_RETRY neuron fires FAILURE but NOT FLOW.

        Regression test for the "infinite loop on retry LIMIT REACHED" bug:
        FLOW axons wired from logic nodes must not fire because logic nodes
        deterministically return SUCCESS or FAILURE from their own evaluation.
        """
        retry_effector = Effector.objects.get(pk=Effector.LOGIC_RETRY)
        book = NeuralPathway.objects.create(name='Retry Test Book')

        retry_neuron = Neuron.objects.create(
            pathway=book,
            effector=retry_effector,
            environment=self.env,
            is_root=True,
        )
        flow_target = Neuron.objects.create(
            pathway=book,
            effector=self.effector,
            environment=self.env,
            is_root=False,
        )
        failure_target = Neuron.objects.create(
            pathway=book,
            effector=self.effector,
            environment=self.env,
            is_root=False,
        )

        flow_type = AxonType.objects.get(id=AxonType.TYPE_FLOW)
        failure_type = AxonType.objects.get(id=AxonType.TYPE_FAILURE)
        Axon.objects.create(
            pathway=book, source=retry_neuron, target=flow_target, type=flow_type
        )
        Axon.objects.create(
            pathway=book,
            source=retry_neuron,
            target=failure_target,
            type=failure_type,
        )

        cns = CNS(pathway_id=book.id)
        with self.captureOnCommitCallbacks(execute=True):
            cns.dispatch_next_wave()

        root_spike = Spike.objects.get(
            spike_train=cns.spike_train, neuron=retry_neuron
        )
        root_spike.status_id = SpikeStatus.FAILED
        root_spike.save()

        mock_fire_spike_delay.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            cns._process_graph_triggers(root_spike)

        children = Spike.objects.filter(
            spike_train=cns.spike_train, provenance=root_spike
        )
        target_neurons = set(children.values_list('neuron_id', flat=True))

        self.assertIn(failure_target.id, target_neurons)
        self.assertNotIn(
            flow_target.id,
            target_neurons,
            'FLOW axon must NOT fire from a logic node',
        )
        self.assertEqual(children.count(), 1)

    @patch('central_nervous_system.central_nervous_system.fire_spike.delay')
    def test_logic_gate_success_does_not_fire_flow_axon(
        self, mock_fire_spike_delay
    ):
        """Assert a successful LOGIC_GATE fires SUCCESS but NOT FLOW."""
        gate_effector = Effector.objects.get(pk=Effector.LOGIC_GATE)
        book = NeuralPathway.objects.create(name='Gate Test Book')

        gate_neuron = Neuron.objects.create(
            pathway=book,
            effector=gate_effector,
            environment=self.env,
            is_root=True,
        )
        flow_target = Neuron.objects.create(
            pathway=book,
            effector=self.effector,
            environment=self.env,
            is_root=False,
        )
        success_target = Neuron.objects.create(
            pathway=book,
            effector=self.effector,
            environment=self.env,
            is_root=False,
        )

        flow_type = AxonType.objects.get(id=AxonType.TYPE_FLOW)
        success_type = AxonType.objects.get(id=AxonType.TYPE_SUCCESS)
        Axon.objects.create(
            pathway=book, source=gate_neuron, target=flow_target, type=flow_type
        )
        Axon.objects.create(
            pathway=book,
            source=gate_neuron,
            target=success_target,
            type=success_type,
        )

        cns = CNS(pathway_id=book.id)
        with self.captureOnCommitCallbacks(execute=True):
            cns.dispatch_next_wave()

        root_spike = Spike.objects.get(
            spike_train=cns.spike_train, neuron=gate_neuron
        )
        root_spike.status_id = SpikeStatus.SUCCESS
        root_spike.save()

        mock_fire_spike_delay.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            cns._process_graph_triggers(root_spike)

        children = Spike.objects.filter(
            spike_train=cns.spike_train, provenance=root_spike
        )
        target_neurons = set(children.values_list('neuron_id', flat=True))

        self.assertIn(success_target.id, target_neurons)
        self.assertNotIn(
            flow_target.id,
            target_neurons,
            'FLOW axon must NOT fire from a logic node',
        )
        self.assertEqual(children.count(), 1)

    @patch('central_nervous_system.central_nervous_system.fire_spike.delay')
    def test_seed_blackboard_populates_root_spike(
        self, mock_fire_spike_delay
    ):
        """Assert CNS(seed_blackboard=...) pre-loads the root spike blackboard.

        Regression test for the MCP `launch_spike_train` blackboard pre-load
        feature. Values passed in at CNS construction time must land on the
        root spike's blackboard before dispatch, so effectors (and downstream
        spikes via provenance copy) can read them.
        """
        cns = CNS(
            pathway_id=self.book.id,
            seed_blackboard={'prompt': 'hello', 'target': 42},
        )

        with self.captureOnCommitCallbacks(execute=True):
            cns.dispatch_next_wave()

        root_spike = Spike.objects.get(
            spike_train=cns.spike_train, neuron=self.neuron1
        )
        self.assertEqual(root_spike.blackboard.get('prompt'), 'hello')
        self.assertEqual(root_spike.blackboard.get('target'), 42)

    @patch('central_nervous_system.central_nervous_system.fire_spike.delay')
    def test_seed_blackboard_propagates_to_child_spike(
        self, mock_fire_spike_delay
    ):
        """Assert seed blackboard flows from root to child via provenance."""
        cns = CNS(
            pathway_id=self.book.id,
            seed_blackboard={'carry': 'through'},
        )

        with self.captureOnCommitCallbacks(execute=True):
            cns.dispatch_next_wave()

        root_spike = Spike.objects.get(
            spike_train=cns.spike_train, neuron=self.neuron1
        )
        root_spike.status_id = SpikeStatus.SUCCESS
        root_spike.save()

        with self.captureOnCommitCallbacks(execute=True):
            cns._process_graph_triggers(root_spike)

        child_spike = Spike.objects.get(
            spike_train=cns.spike_train,
            neuron=self.neuron2,
            provenance=root_spike,
        )
        self.assertEqual(child_spike.blackboard.get('carry'), 'through')

    @patch('central_nervous_system.central_nervous_system.fire_spike.delay')
    def test_no_seed_blackboard_starts_empty(self, mock_fire_spike_delay):
        """Assert omitting seed_blackboard preserves the legacy empty-start."""
        cns = CNS(pathway_id=self.book.id)

        with self.captureOnCommitCallbacks(execute=True):
            cns.dispatch_next_wave()

        root_spike = Spike.objects.get(
            spike_train=cns.spike_train, neuron=self.neuron1
        )
        self.assertEqual(root_spike.blackboard, {})

    @patch('central_nervous_system.central_nervous_system.fire_spike.delay')
    def test_non_logic_success_still_fires_flow_axon(
        self, mock_fire_spike_delay
    ):
        """Assert non-logic neurons retain the FLOW-plus-SUCCESS behavior."""
        book = NeuralPathway.objects.create(name='Non-Logic Flow Book')

        source_neuron = Neuron.objects.create(
            pathway=book,
            effector=self.effector,
            environment=self.env,
            is_root=True,
        )
        flow_target = Neuron.objects.create(
            pathway=book,
            effector=self.effector,
            environment=self.env,
            is_root=False,
        )
        success_target = Neuron.objects.create(
            pathway=book,
            effector=self.effector,
            environment=self.env,
            is_root=False,
        )

        flow_type = AxonType.objects.get(id=AxonType.TYPE_FLOW)
        success_type = AxonType.objects.get(id=AxonType.TYPE_SUCCESS)
        Axon.objects.create(
            pathway=book,
            source=source_neuron,
            target=flow_target,
            type=flow_type,
        )
        Axon.objects.create(
            pathway=book,
            source=source_neuron,
            target=success_target,
            type=success_type,
        )

        cns = CNS(pathway_id=book.id)
        with self.captureOnCommitCallbacks(execute=True):
            cns.dispatch_next_wave()

        root_spike = Spike.objects.get(
            spike_train=cns.spike_train, neuron=source_neuron
        )
        root_spike.status_id = SpikeStatus.SUCCESS
        root_spike.save()

        mock_fire_spike_delay.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            cns._process_graph_triggers(root_spike)

        children = Spike.objects.filter(
            spike_train=cns.spike_train, provenance=root_spike
        )
        target_neurons = set(children.values_list('neuron_id', flat=True))

        self.assertIn(flow_target.id, target_neurons)
        self.assertIn(success_target.id, target_neurons)
        self.assertEqual(children.count(), 2)
