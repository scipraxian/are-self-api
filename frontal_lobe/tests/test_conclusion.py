"""Tests for SessionConclusion push/pull transport.

Mirror of ``test_digest.py``: a signal test class that exercises the
``post_save`` receiver in ``frontal_lobe.signals`` and asserts the
Acetylcholine broadcast wiring, plus a pull-endpoint test class for
``/api/v2/reasoning_sessions/{id}/conclusion/``. A final symmetry
test asserts ``SessionConclusionSerializer(...).data`` equals
``conclusion_to_vesicle(...)`` so push and pull stay byte-identical.
"""

from unittest.mock import AsyncMock, patch

from rest_framework import status
from rest_framework.test import APIClient

from common.tests.common_test_case import CommonTestCase
from frontal_lobe import signals as conclusion_signals
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    SessionConclusion,
)
from frontal_lobe.serializers import SessionConclusionSerializer
from frontal_lobe.signals import conclusion_to_vesicle


def _make_session(test):
    """Create a bare ReasoningSession for conclusion tests to hang off.

    Flat module-level helper (no nested functions) — style guide.
    """
    test.session = ReasoningSession.objects.create(
        status_id=ReasoningStatusID.ACTIVE
    )


def _conclusion_defaults():
    """Canonical field values for a SessionConclusion under test."""
    return dict(
        summary='The session did a thing.',
        reasoning_trace='Trace of the thought process.',
        outcome_status='SUCCESS',
        recommended_action='Ship it.',
        next_goal_suggestion='Do it again, harder.',
        system_persona_and_prompt_feedback='Prompt was fine.',
    )


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------


class SessionConclusionSignalTest(CommonTestCase):
    """Assert the post_save receiver fires Acetylcholine correctly."""

    def setUp(self):
        super().setUp()
        _make_session(self)

    def test_conclusion_post_save_broadcasts_acetylcholine(self):
        """Assert saving a conclusion fires one Acetylcholine vesicle."""
        with patch(
            'frontal_lobe.signals.fire_neurotransmitter',
            new_callable=AsyncMock,
        ) as mock_fire:
            conclusion = SessionConclusion.objects.create(
                session=self.session,
                status_id=ReasoningStatusID.COMPLETED,
                **_conclusion_defaults(),
            )

        self.assertEqual(mock_fire.call_count, 1)
        transmitter = mock_fire.call_args.args[0]
        self.assertEqual(transmitter.receptor_class, 'SessionConclusion')
        self.assertEqual(transmitter.dendrite_id, str(self.session.id))
        self.assertEqual(transmitter.activity, 'saved')
        self.assertEqual(transmitter.vesicle['id'], conclusion.id)
        self.assertEqual(
            transmitter.vesicle['session_id'], str(self.session.id)
        )
        self.assertEqual(transmitter.vesicle['summary'], conclusion.summary)
        self.assertEqual(
            transmitter.vesicle['outcome_status'], 'SUCCESS'
        )

    def test_raw_true_fixture_load_skips_broadcast(self):
        """Assert raw=True fixture loads bypass the receiver."""
        conclusion = SessionConclusion(
            session=self.session,
            status_id=ReasoningStatusID.COMPLETED,
            **_conclusion_defaults(),
        )
        conclusion.save()

        with patch(
            'frontal_lobe.signals.fire_neurotransmitter',
            new_callable=AsyncMock,
        ) as mock_fire:
            conclusion_signals.broadcast_session_conclusion(
                sender=SessionConclusion,
                instance=conclusion,
                raw=True,
                created=False,
                using='default',
                update_fields=None,
            )

        mock_fire.assert_not_called()


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class SessionConclusionEndpointTest(CommonTestCase):
    """Assert /api/v2/reasoning_sessions/{id}/conclusion/ behaves."""

    def setUp(self):
        super().setUp()
        _make_session(self)
        self.client = APIClient()

    def test_conclusion_endpoint_returns_serialized_conclusion(self):
        """Assert a present conclusion returns 200 + the expected shape."""
        conclusion = SessionConclusion.objects.create(
            session=self.session,
            status_id=ReasoningStatusID.COMPLETED,
            **_conclusion_defaults(),
        )

        url = (
            '/api/v2/reasoning_sessions/%s/conclusion/' % self.session.id
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['id'], conclusion.id)
        self.assertEqual(body['session_id'], str(self.session.id))
        self.assertEqual(body['summary'], conclusion.summary)
        self.assertEqual(body['outcome_status'], 'SUCCESS')
        self.assertEqual(body['status_name'], 'Completed')
        self.assertIn('created', body)
        self.assertIn('modified', body)

    def test_conclusion_endpoint_returns_404_when_absent(self):
        """Assert a session with no conclusion returns 404."""
        url = (
            '/api/v2/reasoning_sessions/%s/conclusion/' % self.session.id
        )
        response = self.client.get(url)
        self.assertEqual(
            response.status_code, status.HTTP_404_NOT_FOUND
        )


# ---------------------------------------------------------------------------
# Push/pull shape symmetry
# ---------------------------------------------------------------------------


class SessionConclusionSymmetryTest(CommonTestCase):
    """Assert serializer output matches the Acetylcholine vesicle dict."""

    def setUp(self):
        super().setUp()
        _make_session(self)

    def test_serializer_matches_vesicle(self):
        """Assert SessionConclusionSerializer output == conclusion_to_vesicle."""
        conclusion = SessionConclusion.objects.create(
            session=self.session,
            status_id=ReasoningStatusID.COMPLETED,
            **_conclusion_defaults(),
        )
        vesicle = conclusion_to_vesicle(conclusion)
        serialized = SessionConclusionSerializer(conclusion).data
        self.assertEqual(dict(serialized), vesicle)
