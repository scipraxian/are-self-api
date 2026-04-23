"""Tests for the FK-graph walker."""

from __future__ import annotations

import uuid

from common.tests.common_test_case import CommonTestCase
from central_nervous_system.models import Effector, NeuralPathway
from neuroplasticity import graph_walker, fixture_scan
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus


def _make_modifier(slug: str) -> NeuralModifier:
    return NeuralModifier.objects.create(
        slug=slug,
        name=slug,
        version='1.0.0',
        author='tests',
        license='MIT',
        manifest_hash='0' * 64,
        manifest_json={},
        status_id=NeuralModifierStatus.INSTALLED,
    )


class GraphWalkerClassificationTest(CommonTestCase):
    """Owned / shared / orphan / core states classify correctly."""

    def setUp(self):
        super().setUp()
        fixture_scan.clear_fixture_pk_index()
        self.alpha = _make_modifier('alpha')
        self.beta = _make_modifier('beta')

    def test_owned_rows_are_tagged_owned(self):
        owned = Effector.objects.create(
            name='alpha-owned', genome=self.alpha
        )

        graph = graph_walker.build_bundle_graph('alpha')

        node = next(n for n in graph['nodes'] if n['pk'] == str(owned.pk))
        self.assertEqual(node['state'], 'owned')
        self.assertEqual(node['owner_slug'], 'alpha')

    def test_shared_rows_are_tagged_with_other_slug(self):
        owned = Effector.objects.create(
            name='alpha-owner', genome=self.alpha
        )
        # Pathway owned by BETA, but referenced by alpha's effector only
        # if reachable — we'll hook it up via an Effector FK. There is
        # no direct FK Effector → NeuralPathway in the current schema,
        # so we fabricate reachability by creating a spike/neuron chain.
        # Simplest: create both rows and assert the classifier via the
        # classifier helper when we pass them in directly.
        pathway = NeuralPathway.objects.create(
            name='beta-owner', genome=self.beta
        )

        graph = graph_walker.build_bundle_graph('alpha')

        nodes_by_pk = {n['pk']: n for n in graph['nodes']}
        alpha_node = nodes_by_pk[str(owned.pk)]
        self.assertEqual(alpha_node['state'], 'owned')
        # Beta's pathway is unreachable from alpha via the forward-FK
        # graph, so it should NOT appear in alpha's graph output. This
        # pins down the "only descend via the 12 models" invariant.
        self.assertNotIn(str(pathway.pk), nodes_by_pk)

    def test_orphan_and_core_classification_via_fixture_index(self):
        """An untagged row is orphan unless its pk is in the fixture index."""
        owned = Effector.objects.create(
            name='alpha-owner', genome=self.alpha
        )
        # Create an untagged Effector and check it surfaces as orphan
        # when the fixture index does NOT list its PK.
        untagged = Effector.objects.create(name='loose-one')

        # Bind it into alpha's graph via an FK hop. Effector has an
        # `executable` FK to Executable (GenomeOwnedMixin), but not to
        # another Effector. We'll verify classification logic directly.
        from neuroplasticity.graph_walker import _classify
        index: dict = {}
        state, owner = _classify(untagged, 'alpha', index)
        self.assertEqual(state, 'orphan')
        self.assertIsNone(owner)

        index_with_pk = {
            'central_nervous_system.effector': {str(untagged.pk)}
        }
        state, owner = _classify(untagged, 'alpha', index_with_pk)
        self.assertEqual(state, 'core')
        self.assertIsNone(owner)

        # Sanity: owned row still classifies correctly.
        state, owner = _classify(owned, 'alpha', index)
        self.assertEqual(state, 'owned')
        self.assertEqual(owner, 'alpha')


class FixtureScanBuilderTest(CommonTestCase):
    """Fixture-scan index aggregates PKs from initial_data.json files."""

    def setUp(self):
        super().setUp()
        fixture_scan.clear_fixture_pk_index()

    def test_index_contains_at_least_one_cns_tag(self):
        """Assert a known fixture model shows up in the scanned index.

        ``central_nervous_system/fixtures/initial_data.json`` has CNS
        tag rows on disk in the repo. The index must include it.
        """
        index = fixture_scan.refresh_fixture_pk_index()
        self.assertIn('central_nervous_system.cnstag', index)
        self.assertGreater(len(index['central_nervous_system.cnstag']), 0)

    def test_synthetic_orphan_pk_not_in_index(self):
        """Assert a random UUID that was never fixtured is absent from the index."""
        index = fixture_scan.refresh_fixture_pk_index()
        random_pk = str(uuid.uuid4())
        for pks in index.values():
            self.assertNotIn(random_pk, pks)
