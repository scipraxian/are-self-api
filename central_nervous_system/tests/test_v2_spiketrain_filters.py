from common.tests.common_test_case import CommonTestCase
from central_nervous_system.models import (
    Effector,
    NeuralPathway,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)


class SpikeTrainViewSetV2FilterTest(CommonTestCase):
    fixtures = (
        'parietal_lobe/fixtures/initial_data.json',
        'hypothalamus/fixtures/initial_data.json',
        'temporal_lobe/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
        'central_nervous_system/fixtures/initial_data.json',
    )
    """Assert the V2 spiketrains endpoint correctly filters by query params."""

    V2_URL = '/api/v2/spiketrains/'

    def setUp(self):
        super().setUp()
        self.pathway_a = NeuralPathway.objects.create(name='Pathway A')
        self.pathway_b = NeuralPathway.objects.create(name='Pathway B')

        self.train_a = SpikeTrain.objects.create(
            pathway=self.pathway_a,
            status_id=SpikeTrainStatus.RUNNING,
        )
        self.train_b = SpikeTrain.objects.create(
            pathway=self.pathway_b,
            status_id=SpikeTrainStatus.SUCCESS,
        )

        # Child train with parent_spike for is_root testing
        self.effector = Effector.objects.create(name='test-effector')
        self.parent_spike = Spike.objects.create(
            spike_train=self.train_a,
            effector=self.effector,
            status_id=SpikeStatus.SUCCESS,
        )
        self.child_train = SpikeTrain.objects.create(
            pathway=self.pathway_a,
            status_id=SpikeTrainStatus.RUNNING,
            parent_spike=self.parent_spike,
        )

    def _get_ids(self, response):
        """Extract spike train IDs from a list response."""
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        return {str(r['id']) for r in results}

    def test_filter_by_pathway(self):
        """Assert ?pathway=<uuid> returns only spike trains for that pathway."""
        url = f'{self.V2_URL}?pathway={self.pathway_a.id}'
        response = self.test_client.get(url)
        self.assertEqual(response.status_code, 200)

        ids = self._get_ids(response)
        self.assertIn(str(self.train_a.id), ids)
        self.assertIn(str(self.child_train.id), ids)
        self.assertNotIn(
            str(self.train_b.id),
            ids,
            'Pathway B train must not appear when filtering for Pathway A',
        )

    def test_filter_by_status(self):
        """Assert ?status=<id> returns only spike trains with that status."""
        url = f'{self.V2_URL}?status={SpikeTrainStatus.RUNNING}'
        response = self.test_client.get(url)
        self.assertEqual(response.status_code, 200)

        ids = self._get_ids(response)
        self.assertIn(str(self.train_a.id), ids)
        self.assertNotIn(
            str(self.train_b.id),
            ids,
            'Succeeded train must not appear when filtering for RUNNING',
        )

    def test_filter_is_root(self):
        """Assert ?is_root=true returns only root spike trains (no parent)."""
        url = f'{self.V2_URL}?is_root=true'
        response = self.test_client.get(url)
        self.assertEqual(response.status_code, 200)

        ids = self._get_ids(response)
        self.assertIn(str(self.train_a.id), ids)
        self.assertIn(str(self.train_b.id), ids)
        self.assertNotIn(
            str(self.child_train.id),
            ids,
            'Child train must not appear in is_root=true results',
        )

    def test_filter_is_active_true(self):
        """Assert ?is_active=true returns only alive spike trains."""
        url = f'{self.V2_URL}?is_active=true'
        response = self.test_client.get(url)
        self.assertEqual(response.status_code, 200)

        ids = self._get_ids(response)
        self.assertIn(str(self.train_a.id), ids)
        self.assertNotIn(
            str(self.train_b.id),
            ids,
            'Terminal train must not appear when filtering is_active=true',
        )

    def test_filter_is_active_false(self):
        """Assert ?is_active=false returns only terminal spike trains."""
        url = f'{self.V2_URL}?is_active=false'
        response = self.test_client.get(url)
        self.assertEqual(response.status_code, 200)

        ids = self._get_ids(response)
        self.assertNotIn(
            str(self.train_a.id),
            ids,
            'Running train must not appear when filtering is_active=false',
        )
        self.assertIn(str(self.train_b.id), ids)

    def test_no_filter_returns_all(self):
        """Assert unfiltered list returns all spike trains."""
        response = self.test_client.get(self.V2_URL)
        self.assertEqual(response.status_code, 200)

        ids = self._get_ids(response)
        self.assertIn(str(self.train_a.id), ids)
        self.assertIn(str(self.train_b.id), ids)
        self.assertIn(str(self.child_train.id), ids)
