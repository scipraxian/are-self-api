"""``POST /api/v2/thalamus/clear/`` — mark the current Thalamus session STOPPED.

After ``clear()`` returns, the next ``/interact/`` call falls through
to the GENESIS / FRESH START path in ``ThalamusViewSet.interact``
because the most-recent session on the standing SpikeTrain is no
longer in an active state. Idempotent on the no-active-session path.
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


class ThalamusClearTestCase(CommonFixturesAPITestCase):
    URL = '/api/v2/thalamus/clear/'

    def _make_active_session(self) -> ReasoningSession:
        """Build the standing SpikeTrain + Spike + ReasoningSession chain."""
        pathway = NeuralPathway.objects.get(id=NeuralPathway.THALAMUS)
        train = SpikeTrain.objects.create(
            pathway=pathway,
            environment_id=pathway.environment_id,
            status_id=SpikeTrainStatus.RUNNING,
        )
        spike = Spike.objects.create(
            spike_train=train,
            status_id=1,
            axoplasm={},
        )
        return ReasoningSession.objects.create(
            spike=spike,
            status_id=ReasoningStatusID.ATTENTION_REQUIRED,
            max_turns=50,
            identity_disc_id=IdentityDisc.THALAMUS,
        )

    def test_clear_active_session_marks_stopped(self):
        """Assert clearing an ATTENTION_REQUIRED session flips it to STOPPED."""
        session = self._make_active_session()

        res = self.test_client.post(self.URL, format='json')

        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['ok'])
        self.assertIn('STOPPED', res.json()['message'])
        session.refresh_from_db()
        self.assertEqual(session.status_id, ReasoningStatusID.STOPPED)

    def test_clear_with_no_standing_train_is_a_noop(self):
        """Assert calling clear when no SpikeTrain exists returns 200 ok=True."""
        # Defensive: scrub any THALAMUS SpikeTrains that fixtures may have
        # introduced so the no-train path is the only one reachable.
        SpikeTrain.objects.filter(
            pathway_id=NeuralPathway.THALAMUS
        ).delete()

        res = self.test_client.post(self.URL, format='json')

        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['ok'])
        self.assertIn('nothing to clear', res.json()['message'])

    def test_clear_already_terminal_session_is_a_noop(self):
        """Assert calling clear on a STOPPED session leaves it unchanged."""
        session = self._make_active_session()
        session.status_id = ReasoningStatusID.STOPPED
        session.save(update_fields=['status_id'])

        res = self.test_client.post(self.URL, format='json')

        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['ok'])
        self.assertIn('No active session', res.json()['message'])
        session.refresh_from_db()
        self.assertEqual(session.status_id, ReasoningStatusID.STOPPED)

    def test_messages_skips_stopped_session_after_clear(self):
        """Assert GET /messages/ returns empty after clear, skipping the stopped session.

        Regression: without the ``.exclude(status_id=STOPPED)`` filter
        on the messages query, the just-cleared session's chat history
        would still hydrate the UI until the user typed again.
        """
        session = self._make_active_session()
        # Populate one turn with request_payload so get_chat_history
        # would otherwise return real content from this session.
        usage = AIModelProviderUsageRecord.objects.create(
            identity_disc_id=IdentityDisc.THALAMUS,
            request_payload=[{'role': 'user', 'content': 'hello world'}],
        )
        ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
            model_usage_record=usage,
        )

        # Sanity: messages returns the populated content BEFORE clear.
        pre = self.test_client.get('/api/v2/thalamus/messages/')
        self.assertEqual(pre.status_code, 200, pre.content)
        pre_msgs = pre.json()['messages']
        self.assertTrue(
            any('hello world' in str(m) for m in pre_msgs),
            'precondition: messages should return content before clear',
        )

        # Clear the session.
        clear_res = self.test_client.post(self.URL, format='json')
        self.assertEqual(clear_res.status_code, 200, clear_res.content)

        # After clear, messages must skip the STOPPED session entirely.
        post = self.test_client.get('/api/v2/thalamus/messages/')
        self.assertEqual(post.status_code, 200, post.content)
        self.assertEqual(post.json()['messages'], [])
