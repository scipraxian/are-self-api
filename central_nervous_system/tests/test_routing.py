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
