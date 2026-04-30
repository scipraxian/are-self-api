"""``GET /api/v2/thalamus/model-info/`` -- Thalamus disc's configured-model pill.

``model_name`` and ``context_window`` are a cheap lookup of
``IdentityDisc.THALAMUS.selection_filter.preferred_model.ai_model``
(configured intent, not live routing).  ``current_tokens`` is the
most recent ``ReasoningTurn.model_usage_record.input_tokens`` on the
standing Thalamus session (excluding STOPPED), so a freshly-cleared
chat reports null until the next turn runs.
"""

from __future__ import annotations

from central_nervous_system.models import (
    NeuralPathway,
    Spike,
    SpikeTrain,
    SpikeTrainStatus,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from hypothalamus.models import AIModelProviderUsageRecord
from identity.models import IdentityDisc


class ThalamusModelInfoTestCase(CommonFixturesAPITestCase):
    URL = '/api/v2/thalamus/model-info/'

    def test_returns_200_with_expected_shape(self):
        """Assert the endpoint always returns 200 with the three-field shape."""
        res = self.test_client.get(self.URL)
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIn('model_name', body)
        self.assertIn('context_window', body)
        self.assertIn('current_tokens', body)

    def test_returns_nulls_when_disc_has_no_selection_filter(self):
        """Assert all three fields null when the disc's selection_filter is unset."""
        disc = IdentityDisc.objects.get(id=IdentityDisc.THALAMUS)
        disc.selection_filter = None
        disc.save(update_fields=['selection_filter'])

        res = self.test_client.get(self.URL)

        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIsNone(body['model_name'])
        self.assertIsNone(body['context_window'])
        self.assertIsNone(body['current_tokens'])

    def test_returns_resolved_values_when_chain_is_complete(self):
        """Assert the endpoint returns concrete name + window when the full chain resolves.

        Uses whatever AIModel + AIModelProvider + AIModelSelectionFilter
        rows the fixtures already provide. If the disc isn't pre-wired
        with a selection_filter, the test wires up a synthetic chain
        from the first available model + provider in the test DB.
        """
        from hypothalamus.models import (
            AIModel,
            AIModelProvider,
            AIModelSelectionFilter,
        )

        disc = IdentityDisc.objects.get(id=IdentityDisc.THALAMUS)
        if disc.selection_filter is None:
            model = AIModel.objects.first()
            provider = AIModelProvider.objects.filter(ai_model=model).first()
            if model is None or provider is None:
                self.skipTest(
                    'No AIModel + AIModelProvider available in fixtures '
                    'to exercise the resolved-chain path.'
                )
            sel_filter = AIModelSelectionFilter.objects.create(
                name='thalamus-test-filter',
                preferred_model=provider,
            )
            disc.selection_filter = sel_filter
            disc.save(update_fields=['selection_filter'])

        # Refresh through the same FK chain the endpoint walks.
        disc.refresh_from_db()
        provider = disc.selection_filter.preferred_model
        expected_model = provider.ai_model

        res = self.test_client.get(self.URL)

        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body['model_name'], expected_model.name)
        self.assertEqual(body['context_window'], expected_model.context_length)

    def test_current_tokens_reads_from_most_recent_turn(self):
        """Assert current_tokens reflects the most-recent turn's input_tokens."""
        # Build the standing-train chain on the THALAMUS pathway.
        pathway = NeuralPathway.objects.get(id=NeuralPathway.THALAMUS)
        train = SpikeTrain.objects.create(
            pathway=pathway,
            environment_id=pathway.environment_id,
            status_id=SpikeTrainStatus.RUNNING,
        )
        spike = Spike.objects.create(
            spike_train=train, status_id=1, axoplasm={},
        )
        session = ReasoningSession.objects.create(
            spike=spike,
            status_id=ReasoningStatusID.ATTENTION_REQUIRED,
            max_turns=50,
            identity_disc_id=IdentityDisc.THALAMUS,
        )
        usage = AIModelProviderUsageRecord.objects.create(
            identity_disc_id=IdentityDisc.THALAMUS,
            request_payload=[],
            input_tokens=4242,
        )
        ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
            model_usage_record=usage,
        )

        res = self.test_client.get(self.URL)

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['current_tokens'], 4242)

    def test_current_tokens_null_after_clear(self):
        """Assert current_tokens flips to null when the only session is STOPPED."""
        pathway = NeuralPathway.objects.get(id=NeuralPathway.THALAMUS)
        train = SpikeTrain.objects.create(
            pathway=pathway,
            environment_id=pathway.environment_id,
            status_id=SpikeTrainStatus.RUNNING,
        )
        spike = Spike.objects.create(
            spike_train=train, status_id=1, axoplasm={},
        )
        session = ReasoningSession.objects.create(
            spike=spike,
            status_id=ReasoningStatusID.STOPPED,
            max_turns=50,
            identity_disc_id=IdentityDisc.THALAMUS,
        )
        usage = AIModelProviderUsageRecord.objects.create(
            identity_disc_id=IdentityDisc.THALAMUS,
            request_payload=[],
            input_tokens=999,
        )
        ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
            model_usage_record=usage,
        )

        res = self.test_client.get(self.URL)

        self.assertEqual(res.status_code, 200, res.content)
        # The only session on the standing train is STOPPED, so the
        # endpoint must skip it -- current_tokens is null even though a
        # populated usage record exists.
        self.assertIsNone(res.json()['current_tokens'])
