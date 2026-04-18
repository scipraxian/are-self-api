"""Unit tests for central_nervous_system/sample_pathway.py.

Covers _build_baseline_index (real-fixture scan + malformed-file
resilience) and sample_pathway (subgraph extraction, dependency
closure, baseline filtering, dedup, id-form handling).
"""

import json
import uuid
from unittest.mock import patch

from common.tests.common_test_case import CommonTestCase

from central_nervous_system.models import (
    Axon,
    Effector,
    Neuron,
    NeuronContext,
    NeuralPathway,
)
from central_nervous_system.sample_pathway import (
    _build_baseline_index,
    sample_pathway,
)
from environments.models import Executable


BEGIN_PLAY_UUID = '974ed732-6f2d-47f4-9482-18d17c73086e'


class BuildBaselineIndexTest(CommonTestCase):
    """Verify the baseline tier scanner."""

    def test_returns_set_of_model_pk_tuples(self):
        """Assert the index is a set of (model_label, pk_str) tuples."""
        index = _build_baseline_index()

        self.assertIsInstance(index, set)
        self.assertGreater(len(index), 0)
        sample = next(iter(index))
        self.assertEqual(len(sample), 2)
        self.assertIsInstance(sample[0], str)
        self.assertIsInstance(sample[1], str)

    def test_contains_known_genetic_immutables_row(self):
        """Assert a known genetic_immutables row (BEGIN_PLAY Executable)
        appears in the index — proves the scan actually reached the
        environments/fixtures/genetic_immutables.json file."""
        index = _build_baseline_index()

        self.assertIn(('environments.executable', BEGIN_PLAY_UUID), index)

    def test_pks_are_stringified(self):
        """Assert integer-PK rows (protocol enums) are stored as strings,
        so callers can compare uniformly against UUID-PK rows."""
        index = _build_baseline_index()

        # SpikeStatus is an integer-PK enum in genetic_immutables.
        spike_status_keys = [
            key for key in index
            if key[0] == 'central_nervous_system.spikestatus'
        ]
        self.assertGreater(len(spike_status_keys), 0)
        for _, pk in spike_status_keys:
            self.assertIsInstance(pk, str)

    def test_resilient_to_malformed_fixture_file(self):
        """Assert a JSONDecodeError on one tier file does not crash the
        scan — the bad file is logged and skipped."""
        original_load = json.load
        call_count = {'n': 0}

        def flaky_load(fp, *args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise json.JSONDecodeError('boom', '', 0)
            return original_load(fp, *args, **kwargs)

        with patch(
            'central_nervous_system.sample_pathway.json.load',
            side_effect=flaky_load,
        ):
            index = _build_baseline_index()

        # Scan continued past the bad file and produced a non-empty set.
        self.assertIsInstance(index, set)
        self.assertGreater(len(index), 0)


class SamplePathwayTest(CommonTestCase):
    """Verify subgraph extraction and baseline filtering."""

    def setUp(self):
        super().setUp()
        # Use BEGIN_PLAY as the executable: it lives in
        # environments/fixtures/genetic_immutables.json so we can later
        # assert that the sampler filters it out as baseline.
        self.baseline_executable = Executable.objects.get(id=BEGIN_PLAY_UUID)

        # Test-created effector: NOT in any baseline tier, so the
        # sampler should always include it when dependencies are on.
        self.effector = Effector.objects.create(
            name='Sample Pathway Test Effector',
            executable=self.baseline_executable,
        )

        self.pathway = NeuralPathway.objects.create(name='Sample Test Pathway')
        self.neuron_a = Neuron.objects.create(
            pathway=self.pathway, effector=self.effector
        )
        self.neuron_b = Neuron.objects.create(
            pathway=self.pathway, effector=self.effector
        )
        NeuronContext.objects.create(
            neuron=self.neuron_a, key='probe_key', value='probe_value'
        )
        Axon.objects.create(
            pathway=self.pathway,
            source=self.neuron_a,
            target=self.neuron_b,
        )

    def _records_by_model(self, fixture):
        """Group fixture records by their model label."""
        grouped = {}
        for record in fixture:
            grouped.setdefault(record['model'], []).append(record)
        return grouped

    def test_returns_pathway_neurons_contexts_and_axons(self):
        """Assert the core subgraph (no dependencies) is extracted."""
        fixture = sample_pathway(self.pathway.id, include_dependencies=False)
        grouped = self._records_by_model(fixture)

        self.assertEqual(len(grouped['central_nervous_system.neuralpathway']), 1)
        self.assertEqual(len(grouped['central_nervous_system.neuron']), 2)
        self.assertEqual(len(grouped['central_nervous_system.neuroncontext']), 1)
        self.assertEqual(len(grouped['central_nervous_system.axon']), 1)

    def test_no_dependencies_excludes_effector(self):
        """Assert include_dependencies=False omits the effector even
        though it's referenced by neurons in the subgraph."""
        fixture = sample_pathway(self.pathway.id, include_dependencies=False)
        grouped = self._records_by_model(fixture)

        self.assertNotIn('central_nervous_system.effector', grouped)

    def test_with_dependencies_includes_test_effector(self):
        """Assert dependency closure pulls in the effector when it is
        not already present in the baseline tiers."""
        fixture = sample_pathway(self.pathway.id, include_dependencies=True)
        grouped = self._records_by_model(fixture)

        effector_pks = {r['pk'] for r in grouped['central_nervous_system.effector']}
        self.assertIn(str(self.effector.id), effector_pks)

    def test_baseline_executable_is_filtered_out(self):
        """Assert BEGIN_PLAY (a genetic_immutables Executable) is NOT in
        the sampled fixture — the whole point of the baseline filter."""
        fixture = sample_pathway(self.pathway.id, include_dependencies=True)

        for record in fixture:
            if record['model'] == 'environments.executable':
                self.assertNotEqual(record['pk'], BEGIN_PLAY_UUID)

    def test_dedups_shared_effector_across_neurons(self):
        """Assert a single effector referenced by N neurons appears
        exactly once in the sampled fixture, not N times."""
        fixture = sample_pathway(self.pathway.id, include_dependencies=True)
        grouped = self._records_by_model(fixture)

        effectors = grouped.get('central_nervous_system.effector', [])
        effector_pks = [r['pk'] for r in effectors]
        self.assertEqual(len(effector_pks), len(set(effector_pks)))

    def test_accepts_uuid_object_id(self):
        """Assert a UUID instance is accepted as pathway_id."""
        pathway_uuid = uuid.UUID(str(self.pathway.id))
        fixture = sample_pathway(pathway_uuid, include_dependencies=False)

        grouped = self._records_by_model(fixture)
        self.assertEqual(len(grouped['central_nervous_system.neuralpathway']), 1)

    def test_accepts_string_id(self):
        """Assert a stringified UUID is accepted as pathway_id."""
        fixture = sample_pathway(str(self.pathway.id), include_dependencies=False)

        grouped = self._records_by_model(fixture)
        self.assertEqual(len(grouped['central_nervous_system.neuralpathway']), 1)

    def test_raises_does_not_exist_for_missing_pathway(self):
        """Assert NeuralPathway.DoesNotExist propagates for an
        unknown pathway id rather than being swallowed."""
        bogus_id = uuid.uuid4()

        with self.assertRaises(NeuralPathway.DoesNotExist):
            sample_pathway(bogus_id)

    def test_records_have_django_fixture_format(self):
        """Assert every returned record carries the model/pk/fields keys
        required by Django's loaddata."""
        fixture = sample_pathway(self.pathway.id, include_dependencies=True)

        self.assertGreater(len(fixture), 0)
        for record in fixture:
            self.assertIn('model', record)
            self.assertIn('pk', record)
            self.assertIn('fields', record)


class SamplePathwayEmptySubgraphTest(CommonTestCase):
    """Verify the sampler handles a pathway with no children."""

    def test_pathway_with_no_neurons_returns_only_pathway(self):
        """Assert sampling an empty pathway yields a single record."""
        pathway = NeuralPathway.objects.create(name='Lonely Pathway')

        fixture = sample_pathway(pathway.id, include_dependencies=True)

        self.assertEqual(len(fixture), 1)
        self.assertEqual(fixture[0]['model'], 'central_nervous_system.neuralpathway')
        self.assertEqual(fixture[0]['pk'], str(pathway.id))
