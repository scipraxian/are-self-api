"""API tests for the spike log merge endpoints."""

from django.urls import reverse

from central_nervous_system.models import (
    Effector,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from common.tests.common_test_case import CommonFixturesAPITestCase

MERGE_URL = reverse('v2-spike-log-merge')
MERGE_DELTA_URL = reverse('v2-spike-log-merge-delta')

LOG_CONTENT_A = '[2026.01.08-10.13.29:000][  0]LogTemp: Display: Alpha line\n'
LOG_CONTENT_B = '[2026.01.08-10.13.30:000][  0]LogTemp: Display: Bravo line\n'


class TestSpikeLogMergeAPI(CommonFixturesAPITestCase):
    """API integration tests for N-way spike log merge."""

    def setUp(self):
        super().setUp()
        spike_train = SpikeTrain.objects.create(
            status_id=SpikeTrainStatus.RUNNING,
        )
        self.spike_a = Spike.objects.create(
            spike_train=spike_train,
            status_id=SpikeStatus.SUCCESS,
            effector_id=Effector.BEGIN_PLAY,
            application_log=LOG_CONTENT_A,
        )
        self.spike_b = Spike.objects.create(
            spike_train=spike_train,
            status_id=SpikeStatus.RUNNING,
            effector_id=Effector.BEGIN_PLAY,
            application_log=LOG_CONTENT_B,
        )

    def test_merge_returns_correct_shape(self):
        """Assert full merge endpoint returns expected JSON structure."""
        response = self.test_client.get(
            MERGE_URL,
            {'s1': str(self.spike_a.id), 's2': str(self.spike_b.id)},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn('labels', data)
        self.assertIn('rows', data)
        self.assertIn('cursors', data)
        self.assertIn('any_active', data)
        self.assertEqual(len(data['labels']), 2)
        self.assertGreater(len(data['rows']), 0)
        self.assertTrue(data['any_active'])

    def test_merge_requires_two_spikes(self):
        """Assert merge returns 400 when fewer than 2 spike IDs provided."""
        response = self.test_client.get(MERGE_URL, {'s1': str(self.spike_a.id)})
        self.assertEqual(response.status_code, 400)

    def test_merge_404_on_invalid_spike(self):
        """Assert merge returns 404 for non-existent spike ID."""
        response = self.test_client.get(
            MERGE_URL,
            {
                's1': str(self.spike_a.id),
                's2': '00000000-0000-0000-0000-000000000000',
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_merge_row_has_all_columns(self):
        """Assert each row in the response has a column for each label."""
        response = self.test_client.get(
            MERGE_URL,
            {'s1': str(self.spike_a.id), 's2': str(self.spike_b.id)},
        )
        data = response.json()
        labels = data['labels']
        for row in data['rows']:
            for label in labels:
                self.assertIn(label, row['columns'])

    def test_merge_cursors_keyed_by_spike_id(self):
        """Assert cursors dict uses spike UUIDs as keys."""
        response = self.test_client.get(
            MERGE_URL,
            {'s1': str(self.spike_a.id), 's2': str(self.spike_b.id)},
        )
        data = response.json()
        self.assertIn(str(self.spike_a.id), data['cursors'])
        self.assertIn(str(self.spike_b.id), data['cursors'])

    def test_delta_merge_with_chunks(self):
        """Assert delta endpoint processes provided chunks."""
        response = self.test_client.post(
            MERGE_DELTA_URL,
            {
                'spikes': {
                    str(self.spike_a.id): {
                        'cursor': 0,
                        'chunk': LOG_CONTENT_A,
                    },
                    str(self.spike_b.id): {
                        'cursor': 0,
                        'chunk': LOG_CONTENT_B,
                    },
                },
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data['rows']), 0)

    def test_delta_merge_without_chunk_reads_from_db(self):
        """Assert delta endpoint reads from DB when chunk is omitted."""
        response = self.test_client.post(
            MERGE_DELTA_URL,
            {
                'spikes': {
                    str(self.spike_a.id): {'cursor': 0},
                    str(self.spike_b.id): {'cursor': 0},
                },
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data['rows']), 0)
