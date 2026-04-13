"""Tests for talos_gateway.runtime — canonical gateway-to-reasoning bridge."""

from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from central_nervous_system.models import (
    NeuralPathway,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from identity.models import IdentityDisc
from talos_gateway.models import GatewaySession, GatewaySessionStatusID

THALAMUS_DISC_PK = '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838'
FIRE_SPIKE_PATH = 'thalamus.thalamus.fire_spike'


def _create_standing_train():
    """Create the THALAMUS standing SpikeTrain used by gateway genesis."""
    pathway = NeuralPathway.objects.get(id=NeuralPathway.THALAMUS)
    return SpikeTrain.objects.create(
        pathway=pathway,
        environment_id=pathway.environment_id,
        status_id=SpikeTrainStatus.RUNNING,
    )


def _create_session_with_spike(status_id, spike_status_id=SpikeStatus.RUNNING):
    """Create a ReasoningSession linked to a Spike via the THALAMUS pathway."""
    train = _create_standing_train()
    from central_nervous_system.models import Neuron

    neuron = Neuron.objects.get(pathway_id=NeuralPathway.THALAMUS, is_root=False)
    spike = Spike.objects.create(
        spike_train=train,
        neuron=neuron,
        effector_id=neuron.effector_id,
        status_id=spike_status_id,
        blackboard={},
    )
    session = ReasoningSession.objects.create(
        spike=spike,
        identity_disc_id=THALAMUS_DISC_PK,
        status_id=status_id,
        max_turns=50,
    )
    return session, spike


def _create_gateway_session(reasoning_session, platform='cli', channel_id='test-ch'):
    """Create a GatewaySession pointing at the given reasoning session."""
    return GatewaySession.objects.create(
        platform=platform,
        channel_id=channel_id,
        reasoning_session=reasoning_session,
        status_id=GatewaySessionStatusID.ACTIVE,
        last_activity=timezone.now(),
    )


@override_settings(
    TALOS_GATEWAY={
        'default_identity_disc': THALAMUS_DISC_PK,
        'session_timeout_minutes': 60,
    }
)
class GatewayRuntimeWakeTests(CommonFixturesAPITestCase):
    """Tests for wake_reasoning — the canonical gateway-to-reasoning entrypoint."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    @patch(FIRE_SPIKE_PATH)
    def test_wake_active_session_queues_without_firing_spike(self, mock_fire):
        """Assert wake_reasoning queues message on ACTIVE session without firing spike."""
        from talos_gateway.runtime import wake_reasoning

        session, spike = _create_session_with_spike(ReasoningStatusID.ACTIVE)
        gs = _create_gateway_session(session)

        result = wake_reasoning(gs, session, 'hello there')

        session.refresh_from_db()
        self.assertEqual(result['action'], 'queued')
        self.assertTrue(result['success'])
        self.assertEqual(len(session.swarm_message_queue), 1)
        self.assertEqual(session.swarm_message_queue[0]['content'], 'hello there')
        mock_fire.delay.assert_not_called()

    @patch(FIRE_SPIKE_PATH)
    def test_wake_attention_required_session_fires_spike(self, mock_fire):
        """Assert wake_reasoning transitions ATTENTION_REQUIRED to ACTIVE and fires spike."""
        from talos_gateway.runtime import wake_reasoning

        session, spike = _create_session_with_spike(
            ReasoningStatusID.ATTENTION_REQUIRED,
        )
        gs = _create_gateway_session(session)

        result = wake_reasoning(gs, session, 'wake up')

        session.refresh_from_db()
        self.assertEqual(result['action'], 'woken')
        self.assertTrue(result['success'])
        self.assertEqual(session.status_id, ReasoningStatusID.ACTIVE)
        self.assertEqual(len(session.swarm_message_queue), 1)
        mock_fire.delay.assert_called_once_with(spike.id)

    @patch(FIRE_SPIKE_PATH)
    def test_wake_new_session_creates_spike_and_fires(self, mock_fire):
        """Assert wake_reasoning creates Spike for session with no spike."""
        from talos_gateway.runtime import wake_reasoning

        session = ReasoningSession.objects.create(
            identity_disc_id=THALAMUS_DISC_PK,
            status_id=ReasoningStatusID.PENDING,
            max_turns=50,
        )
        gs = _create_gateway_session(session)

        result = wake_reasoning(gs, session, 'brand new')

        session.refresh_from_db()
        self.assertEqual(result['action'], 'spawned')
        self.assertTrue(result['success'])
        self.assertIsNotNone(session.spike_id)
        self.assertEqual(session.status_id, ReasoningStatusID.ACTIVE)
        self.assertEqual(len(session.swarm_message_queue), 1)
        mock_fire.delay.assert_called_once()
        # Verify spike was created correctly
        spike = Spike.objects.get(id=session.spike_id)
        self.assertEqual(spike.effector_id, 8)  # FRONTAL_LOBE

    @patch(FIRE_SPIKE_PATH)
    def test_wake_completed_session_creates_new_spike(self, mock_fire):
        """Assert wake_reasoning creates new Spike for COMPLETED session."""
        from talos_gateway.runtime import wake_reasoning

        session, old_spike = _create_session_with_spike(
            ReasoningStatusID.COMPLETED,
            spike_status_id=SpikeStatus.SUCCESS,
        )
        gs = _create_gateway_session(session)
        old_spike_id = old_spike.id

        result = wake_reasoning(gs, session, 'start again')

        session.refresh_from_db()
        self.assertEqual(result['action'], 'spawned')
        self.assertTrue(result['success'])
        self.assertNotEqual(session.spike_id, old_spike_id)
        mock_fire.delay.assert_called_once()

    @patch(FIRE_SPIKE_PATH)
    def test_wake_pending_with_spike_queues_only(self, mock_fire):
        """Assert wake_reasoning queues on PENDING session with existing spike."""
        from talos_gateway.runtime import wake_reasoning

        session, spike = _create_session_with_spike(
            ReasoningStatusID.PENDING,
            spike_status_id=SpikeStatus.PENDING,
        )
        gs = _create_gateway_session(session)

        result = wake_reasoning(gs, session, 'queued early')

        session.refresh_from_db()
        self.assertEqual(result['action'], 'queued')
        self.assertEqual(len(session.swarm_message_queue), 1)
        mock_fire.delay.assert_not_called()


@override_settings(
    TALOS_GATEWAY={
        'default_identity_disc': THALAMUS_DISC_PK,
        'session_timeout_minutes': 60,
    }
)
class GatewayHandleInterruptTests(CommonFixturesAPITestCase):
    """Tests for handle_interrupt — spike cancellation from gateway."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    def test_interrupt_sets_spike_to_stopping(self):
        """Assert handle_interrupt sets RUNNING spike to STOPPING."""
        from talos_gateway.runtime import handle_interrupt

        session, spike = _create_session_with_spike(
            ReasoningStatusID.ACTIVE,
            spike_status_id=SpikeStatus.RUNNING,
        )

        result = handle_interrupt(session.id)

        spike.refresh_from_db()
        self.assertTrue(result['success'])
        self.assertEqual(spike.status_id, SpikeStatus.STOPPING)

    def test_interrupt_pending_spike_sets_stopping(self):
        """Assert handle_interrupt sets PENDING spike to STOPPING."""
        from talos_gateway.runtime import handle_interrupt

        session, spike = _create_session_with_spike(
            ReasoningStatusID.PENDING,
            spike_status_id=SpikeStatus.PENDING,
        )

        result = handle_interrupt(session.id)

        spike.refresh_from_db()
        self.assertTrue(result['success'])
        self.assertEqual(spike.status_id, SpikeStatus.STOPPING)

    def test_interrupt_no_spike_returns_error(self):
        """Assert handle_interrupt returns error when session has no spike."""
        from talos_gateway.runtime import handle_interrupt

        session = ReasoningSession.objects.create(
            identity_disc_id=THALAMUS_DISC_PK,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=50,
        )

        result = handle_interrupt(session.id)

        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'no_active_spike')

    def test_interrupt_completed_spike_returns_error(self):
        """Assert handle_interrupt returns error when spike already finished."""
        from talos_gateway.runtime import handle_interrupt

        session, spike = _create_session_with_spike(
            ReasoningStatusID.COMPLETED,
            spike_status_id=SpikeStatus.SUCCESS,
        )

        result = handle_interrupt(session.id)

        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'spike_not_active')

    def test_interrupt_nonexistent_session_returns_error(self):
        """Assert handle_interrupt returns error for unknown session ID."""
        from uuid import uuid4

        from talos_gateway.runtime import handle_interrupt

        result = handle_interrupt(uuid4())

        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'session_not_found')
