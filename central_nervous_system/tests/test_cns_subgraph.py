from unittest.mock import patch

from django.test import TransactionTestCase

from central_nervous_system.central_nervous_system import CNS
from central_nervous_system.models import (
    Effector,
    NeuralPathway,
    Neuron,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from environments.models import ProjectEnvironment


class CNSSubGraphTests(TransactionTestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Base Environment
        self.env = ProjectEnvironment.objects.first()

        # 2. Pathways
        self.parent_pathway = NeuralPathway.objects.create(
            name='Parent Pathway'
        )
        self.child_pathway = NeuralPathway.objects.create(name='Child Pathway')

        # 3. Base dummy effector
        self.dummy_effector = Effector.objects.create(name='Dummy Effector')

        # 4. The Delegation Node (A Neuron that invokes another pathway)
        self.delegation_neuron = Neuron.objects.create(
            pathway=self.parent_pathway,
            effector=self.dummy_effector,
            invoked_pathway=self.child_pathway,
        )

        # 5. Parent Execution State
        self.parent_train = SpikeTrain.objects.create(
            environment=self.env,
            pathway=self.parent_pathway,
            status_id=SpikeTrainStatus.RUNNING,
        )
        self.parent_spike = Spike.objects.create(
            spike_train=self.parent_train,
            neuron=self.delegation_neuron,
            effector=self.dummy_effector,
            status_id=SpikeStatus.CREATED,
        )

        # 6. Instantiate the Orchestrator
        self.cns = CNS(spike_train_id=self.parent_train.id)

    @patch('central_nervous_system.central_nervous_system.CNS.start')
    def test_spawn_subgraph(self, mock_child_start):
        """
        Validates that CNS safely puts the parent spike to sleep,
        creates the child train, and triggers its execution.
        """

        # Execute the brain surgery
        self.cns._spawn_subgraph(self.parent_spike)

        # 1. Verify Parent Spike is put to sleep
        self.parent_spike.refresh_from_db()
        self.assertEqual(
            self.parent_spike.status_id,
            SpikeStatus.DELEGATED,
            'Parent spike must be marked DELEGATED.',
        )

        # 2. Verify Child SpikeTrain was created correctly
        child_train = SpikeTrain.objects.filter(
            parent_spike=self.parent_spike
        ).first()
        self.assertIsNotNone(child_train, 'Child SpikeTrain was not created.')
        self.assertEqual(child_train.pathway, self.child_pathway)
        self.assertEqual(child_train.environment, self.env)
        self.assertEqual(child_train.status_id, SpikeTrainStatus.CREATED)

        # 3. Verify the kickoff was queued in the transaction
        # Because we use TransactionTestCase, on_commit hooks fire immediately
        mock_child_start.assert_called_once()

    @patch.object(CNS, '_spawn_subgraph')
    def test_create_spike_routes_to_subgraph(self, mock_spawn):
        """
        Validates the routing logic inside `_create_spike_from_node`
        actually detects the invoked_pathway and fires the new method.
        """
        # Call the higher level router
        self.cns._create_spike_from_node(
            neuron=self.delegation_neuron, provenance=None
        )

        # Verify it intercepted the node and routed it to our new logic
        mock_spawn.assert_called_once()
