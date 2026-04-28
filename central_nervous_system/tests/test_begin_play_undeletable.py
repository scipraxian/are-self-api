"""``DELETE /api/v2/neurons/<id>/`` — Begin Play neurons are undeletable.

Every NeuralPathway must always carry at least one Begin Play neuron to
fire from. The model-level guard in ``Neuron.delete()`` plus the viewset
``destroy`` translation make it 100% impossible for a pathway to exist
without a Begin Play. CASCADE-from-pathway-delete still removes the
Begin Play row when the pathway itself is being deleted — Django's
Collector uses bulk ``QuerySet.delete()`` which bypasses
``Neuron.delete()``.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from central_nervous_system.models import (
    BEGIN_PLAY_UNDELETABLE,
    Effector,
    NeuralPathway,
    Neuron,
)
from common.tests.common_test_case import CommonFixturesAPITestCase


class BeginPlayUndeletableTestCase(CommonFixturesAPITestCase):
    def setUp(self):
        super().setUp()
        self.pathway = NeuralPathway.objects.create(name='Undeletable Pathway')
        self.begin_play = Neuron.objects.create(
            pathway=self.pathway,
            effector_id=Effector.BEGIN_PLAY,
            is_root=True,
        )
        self.regular = Neuron.objects.create(
            pathway=self.pathway,
            effector_id=Effector.LOGIC_GATE,
        )

    def test_api_delete_on_begin_play_returns_400(self):
        """Assert DELETE on a pathway's only Begin Play returns 400 and the row stays."""
        url = '/api/v2/neurons/{0}/'.format(self.begin_play.id)
        res = self.test_client.delete(url)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('Begin Play', res.json()['detail'])
        self.assertTrue(Neuron.objects.filter(pk=self.begin_play.pk).exists())

    def test_api_delete_response_message_matches_constant(self):
        """Assert the 400 detail is exactly the model-level constant."""
        url = '/api/v2/neurons/{0}/'.format(self.begin_play.id)
        res = self.test_client.delete(url)
        self.assertEqual(res.json()['detail'], BEGIN_PLAY_UNDELETABLE)

    def test_api_delete_on_regular_neuron_succeeds(self):
        """Assert DELETE on a non-Begin-Play neuron returns 204 and removes the row."""
        url = '/api/v2/neurons/{0}/'.format(self.regular.id)
        res = self.test_client.delete(url)
        self.assertEqual(res.status_code, 204, res.content)
        self.assertFalse(Neuron.objects.filter(pk=self.regular.pk).exists())

    def test_pathway_delete_cascades_begin_play_away(self):
        """Assert deleting the pathway still removes its Begin Play via CASCADE."""
        begin_play_pk = self.begin_play.pk
        self.pathway.delete()
        self.assertFalse(Neuron.objects.filter(pk=begin_play_pk).exists())

    def test_model_level_delete_on_begin_play_raises(self):
        """Assert direct ORM ``.delete()`` on a Begin Play neuron raises before super()."""
        with self.assertRaises(ValidationError):
            self.begin_play.delete()
        self.assertTrue(Neuron.objects.filter(pk=self.begin_play.pk).exists())

    def test_redundant_begin_play_is_deletable(self):
        """Assert if a pathway has two Begin Plays, deleting one is allowed."""
        second = Neuron.objects.create(
            pathway=self.pathway,
            effector_id=Effector.BEGIN_PLAY,
        )
        url = '/api/v2/neurons/{0}/'.format(second.id)
        res = self.test_client.delete(url)
        self.assertEqual(res.status_code, 204, res.content)
        # Original Begin Play still there.
        self.assertTrue(Neuron.objects.filter(pk=self.begin_play.pk).exists())
        # The redundant one is gone.
        self.assertFalse(Neuron.objects.filter(pk=second.pk).exists())
