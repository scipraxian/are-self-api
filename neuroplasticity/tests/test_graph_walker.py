"""Tests for the FK-graph walker under the three-state Canonical Genome model."""

from __future__ import annotations

from common.tests.common_test_case import CommonTestCase
from central_nervous_system.models import Effector, NeuralPathway
from neuroplasticity import graph_walker
from neuroplasticity.graph_walker import _classify
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
    """canonical / owned / shared-with / user states classify correctly."""

    def setUp(self):
        super().setUp()
        self.alpha = _make_modifier('alpha')
        self.beta = _make_modifier('beta')

    def test_owned_rows_are_tagged_owned(self):
        """Assert a row genome-stamped with this bundle classifies as owned."""
        owned = Effector.objects.create(
            name='alpha-owned', genome=self.alpha
        )

        graph = graph_walker.build_bundle_graph('alpha')

        node = next(n for n in graph['nodes'] if n['pk'] == str(owned.pk))
        self.assertEqual(node['state'], 'owned')
        self.assertEqual(node['owner_slug'], 'alpha')

    def test_shared_rows_unreachable_from_other_bundle(self):
        """Assert rows owned by a different bundle are NOT walked from alpha."""
        Effector.objects.create(name='alpha-owner', genome=self.alpha)
        pathway = NeuralPathway.objects.create(
            name='beta-owner', genome=self.beta
        )

        graph = graph_walker.build_bundle_graph('alpha')

        pks = {n['pk'] for n in graph['nodes']}
        self.assertNotIn(str(pathway.pk), pks)

    def test_classify_canonical(self):
        """Assert a canonical-stamped row classifies as 'canonical'."""
        canonical_eff = Effector.objects.create(name='canon-row')
        canonical_eff.genome_id = NeuralModifier.CANONICAL
        canonical_eff.save()

        state, owner = _classify(canonical_eff, 'alpha')
        self.assertEqual(state, 'canonical')
        self.assertEqual(owner, NeuralModifier.CANONICAL_SLUG)

    def test_classify_user_for_null_genome(self):
        """Assert a NULL-genome row classifies as 'user' (not orphan/core)."""
        untagged = Effector.objects.create(name='user-row')

        state, owner = _classify(untagged, 'alpha')
        self.assertEqual(state, 'user')
        self.assertIsNone(owner)

    def test_classify_shared_with_other_bundle(self):
        """Assert a row owned by another bundle classifies as 'shared-with'."""
        beta_owned = Effector.objects.create(
            name='beta-owner', genome=self.beta
        )

        state, owner = _classify(beta_owned, 'alpha')
        self.assertEqual(state, 'shared-with beta')
        self.assertEqual(owner, 'beta')
