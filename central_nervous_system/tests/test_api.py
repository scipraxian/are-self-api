from rest_framework.test import APIClient

from common.tests.common_test_case import CommonFixturesAPITestCase
from central_nervous_system.models import NeuralPathway, SpikeTrain, Spike, Effector, SpikeStatus, SpikeTrainStatus


class CNSApiTest(CommonFixturesAPITestCase):

    def setUp(self):
        self.api_client = APIClient()
        self.pathway = NeuralPathway.objects.create(name='Test Pathway')

        # Create root train
        self.root_train = SpikeTrain.objects.create(
            pathway=self.pathway, status_id=SpikeTrainStatus.RUNNING)

        # Create effector and parent spike
        self.effector = Effector.objects.create(name='echo')
        self.parent_spike = Spike.objects.create(spike_train=self.root_train,
                                                 effector=self.effector,
                                                 status_id=SpikeStatus.SUCCESS)

        # Create child train linked to parent spike
        self.child_train = SpikeTrain.objects.create(
            pathway=self.pathway,
            status_id=SpikeTrainStatus.RUNNING,
            parent_spike=self.parent_spike)

    def test_spike_trains_endpoints(self):
        # Test lists
        response = self.api_client.get('/api/v1/spike_trains/')
        self.assertEqual(response.status_code, 200)

        # Test is_root filter
        response = self.api_client.get('/api/v1/spike_trains/?is_root=true')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        root_ids = [str(r['id']) for r in results]

        self.assertIn(str(self.root_train.id), root_ids)
        self.assertNotIn(str(self.child_train.id), root_ids)

        # Test spikes filter
        response = self.api_client.get(
            f'/api/v1/spikes/?spike_train_id={self.root_train.id}')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        spike_ids = [str(r['id']) for r in results]

        self.assertIn(str(self.parent_spike.id), spike_ids)
