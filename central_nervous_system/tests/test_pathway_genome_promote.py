"""``PATCH /api/v2/neuralpathways/<id>/`` — promote pathway + cascade children.

A genome PATCH on the pathway fans out to its direct cascade children
(``Neuron``, ``Axon``, ``NeuronContext``) inside one ``transaction.atomic``
block, then triggers the standard install/uninstall coordinated restart
so workers pick up the new bundle's code paths.

Tests mock ``trigger_system_restart`` on every method that hits the
PATCH endpoint — the un-mocked path spawns a real Celery worker and
reloads the live dev Daphne (per CLAUDE.md).
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from central_nervous_system.models import (
    Axon,
    AxonType,
    Effector,
    NeuralPathway,
    Neuron,
    NeuronContext,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus


def _make_bundle(slug: str) -> NeuralModifier:
    return NeuralModifier.objects.create(
        slug=slug,
        name=slug,
        version='0.1.0',
        author='test',
        license='MIT',
        manifest_hash='',
        manifest_json={},
        status_id=NeuralModifierStatus.INSTALLED,
    )


def _make_broken_bundle(slug: str) -> NeuralModifier:
    return NeuralModifier.objects.create(
        slug=slug,
        name=slug,
        version='0.1.0',
        author='test',
        license='MIT',
        manifest_hash='',
        manifest_json={},
        status_id=NeuralModifierStatus.BROKEN,
    )


_PATCH_PATH = (
    'neuroplasticity.serializer_mixins.trigger_system_restart'
)


class PathwayGenomePromoteTestCase(CommonFixturesAPITestCase):
    def setUp(self):
        super().setUp()
        self.target_bundle = _make_bundle('pathway-target')

        self.pathway = NeuralPathway.objects.create(name='Promote Pathway')
        self.neuron_a = Neuron.objects.create(
            pathway=self.pathway, effector_id=Effector.BEGIN_PLAY
        )
        self.neuron_b = Neuron.objects.create(
            pathway=self.pathway, effector_id=Effector.BEGIN_PLAY
        )
        self.axon_one = Axon.objects.create(
            pathway=self.pathway,
            source=self.neuron_a,
            target=self.neuron_b,
            type_id=AxonType.TYPE_FLOW,
        )
        self.axon_two = Axon.objects.create(
            pathway=self.pathway,
            source=self.neuron_b,
            target=self.neuron_a,
            type_id=AxonType.TYPE_SUCCESS,
        )
        self.context_a = NeuronContext.objects.create(
            neuron=self.neuron_a, key='k1', value='v1'
        )
        self.context_b = NeuronContext.objects.create(
            neuron=self.neuron_b, key='k2', value='v2'
        )
        self._url = '/api/v2/neuralpathways/{0}/'.format(self.pathway.id)

    @patch(_PATCH_PATH)
    def test_genome_change_fans_out_to_children(self, mock_restart):
        """Assert PATCH genome fans the new value to neurons, axons, and contexts."""
        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.pathway.refresh_from_db()
        self.assertEqual(self.pathway.genome_id, self.target_bundle.id)
        for child in (
            self.neuron_a,
            self.neuron_b,
            self.axon_one,
            self.axon_two,
            self.context_a,
            self.context_b,
        ):
            child.refresh_from_db()
            self.assertEqual(child.genome_id, self.target_bundle.id)

    @patch(_PATCH_PATH)
    def test_no_op_patch_does_not_fan_out_or_restart(self, mock_restart):
        """Assert PATCH genome to the current value does not restart or refresh children."""
        original_genome_id = self.pathway.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(original_genome_id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertNotIn('restart_imminent', res.json())
        mock_restart.assert_not_called()
        for child in (
            self.neuron_a,
            self.axon_one,
            self.context_a,
        ):
            child.refresh_from_db()
            self.assertEqual(child.genome_id, original_genome_id)

    @patch(_PATCH_PATH)
    def test_patch_into_canonical_refused(self, mock_restart):
        """Assert PATCH genome=CANONICAL returns 400 and leaves rows unchanged."""
        original_genome_id = self.pathway.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(NeuralModifier.CANONICAL)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.pathway.refresh_from_db()
        self.assertEqual(self.pathway.genome_id, original_genome_id)
        for child in (self.neuron_a, self.axon_one, self.context_a):
            child.refresh_from_db()
            self.assertEqual(child.genome_id, original_genome_id)

    @patch(_PATCH_PATH)
    def test_patch_out_of_canonical_refused(self, mock_restart):
        """Assert PATCH on a CANONICAL-owned pathway returns 400."""
        NeuralPathway.objects.filter(pk=self.pathway.pk).update(
            genome=NeuralModifier.CANONICAL,
        )

        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.pathway.refresh_from_db()
        self.assertEqual(self.pathway.genome_id, NeuralModifier.CANONICAL)

    @patch(_PATCH_PATH)
    def test_patch_to_non_installed_genome_refused(self, mock_restart):
        """Assert PATCH genome to a BROKEN bundle returns 400."""
        broken = _make_broken_bundle('pathway-broken')
        original_genome_id = self.pathway.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(broken.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.pathway.refresh_from_db()
        self.assertEqual(self.pathway.genome_id, original_genome_id)

    @patch(_PATCH_PATH)
    def test_response_includes_restart_imminent_when_genome_moved(
        self, mock_restart,
    ):
        """Assert response payload carries restart_imminent=True on a real move."""
        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json().get('restart_imminent'))
        mock_restart.assert_called_once()

    @patch(_PATCH_PATH)
    def test_child_in_other_bundle_picks_up_new_genome(self, mock_restart):
        """Assert children that started in a different bundle still pick up the new genome."""
        other_bundle = _make_bundle('pathway-other')
        # Pin neuron_b and axon_two to a different bundle than the parent.
        Neuron.objects.filter(pk=self.neuron_b.pk).update(
            genome=other_bundle,
        )
        Axon.objects.filter(pk=self.axon_two.pk).update(genome=other_bundle)
        NeuronContext.objects.filter(pk=self.context_b.pk).update(
            genome=other_bundle,
        )

        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.neuron_b.refresh_from_db()
        self.axon_two.refresh_from_db()
        self.context_b.refresh_from_db()
        self.assertEqual(self.neuron_b.genome_id, self.target_bundle.id)
        self.assertEqual(self.axon_two.genome_id, self.target_bundle.id)
        self.assertEqual(self.context_b.genome_id, self.target_bundle.id)

