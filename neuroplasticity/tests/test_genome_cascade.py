"""Tests for the pathway-rooted genome cascade.

Reach traverses both GenomeOwnedMixin rows (the bundle-eligible models)
and a small set of explicit transit models (Neuron / Axon /
NeuronContext) so the walker can step from a Pathway through its
neurons to the GenomeOwnedMixin Effectors on the other side.

The cascade is **additive** — it claims `genome=NULL` rows for the
target, leaves canonical / cross-bundle rows alone, and refuses only
when the starting pathway itself is canonical-owned. Reach hitting
canonical-owned infrastructure (the default Effector.executable for
example, which is fixture-canonical) is normal — bundles legitimately
reference shared canonical content.
"""

from __future__ import annotations

from common.tests.common_test_case import CommonTestCase
from central_nervous_system.models import (
    Axon,
    Effector,
    NeuralPathway,
    Neuron,
)
from neuroplasticity.genome_cascade import (
    GenomeCascadeConflict,
    cascade_pathway_genome,
    reachable_genome_rows,
)
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


def _build_pathway(name: str = 'pw') -> tuple:
    """Build a small self-contained pathway: pathway + 2 neurons + axon
    + a shared Effector. Returns ``(pathway, neuron_a, neuron_b, axon,
    effector)``. Pathway and Effector are GenomeOwnedMixin (will be
    stamped by the cascade); Neuron and Axon are transit-only. The
    Effector inherits the fixture-canonical default Executable, which
    the cascade reaches via Effector.executable but skips silently
    because it's canonical-owned shared infrastructure.
    """
    pathway = NeuralPathway.objects.create(name=name)
    effector = Effector.objects.create(name='{0}-eff'.format(name))
    neuron_a = Neuron.objects.create(
        pathway=pathway,
        effector=effector,
        is_root=True,
        ui_json='{}',
    )
    neuron_b = Neuron.objects.create(
        pathway=pathway,
        effector=effector,
        is_root=False,
        ui_json='{}',
    )
    axon = Axon.objects.create(
        pathway=pathway,
        source=neuron_a,
        target=neuron_b,
    )
    return pathway, neuron_a, neuron_b, axon, effector


class CascadeReachTest(CommonTestCase):
    """The BFS reach walks through transit models to GenomeOwnedMixin children."""

    def test_reach_includes_pathway_neurons_axon_and_effector(self):
        """Assert reach from a pathway covers transit nodes and the Effector."""
        pathway, neuron_a, neuron_b, axon, effector = _build_pathway('reach')

        rows = reachable_genome_rows(pathway)

        keys = {(type(r)._meta.model_name, str(r.pk)) for r in rows}
        # Pathway and Effector — bundle-eligible, will be stamped
        self.assertIn(('neuralpathway', str(pathway.pk)), keys)
        self.assertIn(('effector', str(effector.pk)), keys)
        # Neuron + Axon — transit, present in reach but not stamped
        self.assertIn(('neuron', str(neuron_a.pk)), keys)
        self.assertIn(('neuron', str(neuron_b.pk)), keys)
        self.assertIn(('axon', str(axon.pk)), keys)


class CascadeStampTest(CommonTestCase):
    """Happy-path stamp + clear cycle on a fresh user-NULL pathway."""

    def setUp(self):
        super().setUp()
        self.alpha = _make_modifier('alpha')

    def test_stamp_writes_genome_on_user_owned_rows_only(self):
        """Assert stamping claims NULL rows (pathway + effector), not the
        canonical Executable that lives in reach by virtue of the
        Effector.executable default."""
        pathway, na, nb, axon, effector = _build_pathway('stamp')

        result = cascade_pathway_genome(pathway, self.alpha)

        self.assertEqual(result['target_slug'], 'alpha')
        # Pathway + Effector — both NULL, both claimed.
        self.assertEqual(result['stamped'], 2)
        # Canonical Executable in reach — skipped silently.
        self.assertGreaterEqual(result['skipped'], 1)
        pathway.refresh_from_db()
        effector.refresh_from_db()
        self.assertEqual(pathway.genome_id, self.alpha.pk)
        self.assertEqual(effector.genome_id, self.alpha.pk)

    def test_clear_reverts_owned_reach_to_null(self):
        """Assert target=None reverts rows owned by the pathway's current
        bundle and leaves canonical infrastructure alone."""
        pathway, _, _, _, effector = _build_pathway('clear')
        cascade_pathway_genome(pathway, self.alpha)

        result = cascade_pathway_genome(pathway, None)

        self.assertIsNone(result['target_slug'])
        # Pathway + Effector reverted; canonical Executable left alone.
        self.assertEqual(result['stamped'], 2)
        self.assertGreaterEqual(result['skipped'], 1)
        pathway.refresh_from_db()
        effector.refresh_from_db()
        self.assertIsNone(pathway.genome_id)
        self.assertIsNone(effector.genome_id)

    def test_clear_on_unowned_pathway_is_noop(self):
        """Assert clear on a NULL-genome pathway does nothing."""
        pathway, _, _, _, _ = _build_pathway('noop')

        result = cascade_pathway_genome(pathway, None)

        self.assertEqual(result['stamped'], 0)
        self.assertEqual(result['skipped'], 0)

    def test_stamp_idempotent(self):
        """Assert a second stamp with the same target reports unchanged."""
        pathway, _, _, _, _ = _build_pathway('idem')
        cascade_pathway_genome(pathway, self.alpha)

        result = cascade_pathway_genome(pathway, self.alpha)

        self.assertEqual(result['stamped'], 0)
        self.assertEqual(result['unchanged'], 2)


class CascadePolicyTest(CommonTestCase):
    """Additive-policy specifics: cross-bundle and canonical reach are
    skipped silently; only a canonical starting pathway refuses."""

    def setUp(self):
        super().setUp()
        self.alpha = _make_modifier('alpha')
        self.beta = _make_modifier('beta')

    def test_other_bundle_in_reach_skipped_silently(self):
        """Assert a beta-owned Effector in alpha's cascade reach is left
        alone; the cascade succeeds for everything else."""
        pathway, _, _, _, effector = _build_pathway('shared')
        # Pre-stamp the Effector as beta-owned. Alpha's cascade must
        # not steal it; it should still claim the (NULL) pathway.
        effector.genome = self.beta
        effector.save(update_fields=['genome'])

        result = cascade_pathway_genome(pathway, self.alpha)

        # Pathway claimed; Effector left at beta; canonical Executable
        # left alone.
        pathway.refresh_from_db()
        effector.refresh_from_db()
        self.assertEqual(pathway.genome_id, self.alpha.pk)
        self.assertEqual(effector.genome_id, self.beta.pk)
        self.assertEqual(result['stamped'], 1)
        self.assertGreaterEqual(result['skipped'], 2)  # beta + canonical

    def test_canonical_in_reach_skipped_silently(self):
        """Assert a canonical Effector in reach is left alone; the
        cascade still claims the user-owned pathway."""
        pathway, _, _, _, effector = _build_pathway('shared-core')
        effector.genome_id = NeuralModifier.CANONICAL
        effector.save(update_fields=['genome'])

        result = cascade_pathway_genome(pathway, self.alpha)

        pathway.refresh_from_db()
        effector.refresh_from_db()
        self.assertEqual(pathway.genome_id, self.alpha.pk)
        self.assertEqual(effector.genome_id, NeuralModifier.CANONICAL)
        self.assertEqual(result['stamped'], 1)
        self.assertGreaterEqual(result['skipped'], 2)  # effector + executable

    def test_canonical_pathway_refuses(self):
        """Assert the cascade refuses to claim a canonical-owned pathway.

        This is the only refusal case — bundles cannot take ownership
        of pathways that ship in core fixtures.
        """
        pathway, _, _, _, _ = _build_pathway('canon-pathway')
        pathway.genome_id = NeuralModifier.CANONICAL
        pathway.save(update_fields=['genome'])

        with self.assertRaises(GenomeCascadeConflict) as ctx:
            cascade_pathway_genome(pathway, self.alpha)

        self.assertEqual(len(ctx.exception.conflicts), 1)
        self.assertEqual(ctx.exception.conflicts[0]['owned_by'], 'canonical')

        pathway.refresh_from_db()
        self.assertEqual(pathway.genome_id, NeuralModifier.CANONICAL)
