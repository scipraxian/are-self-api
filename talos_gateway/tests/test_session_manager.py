"""Tests for talos_gateway.session_manager."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.models import ReasoningSession
from talos_gateway.contracts import PlatformEnvelope
from talos_gateway.models import GatewaySession
from talos_gateway.session_manager import SessionManager

THALAMUS_DISC_PK = '15ca85b8-59a9-4cb6-9fd8-bfd2be47b838'
ALT_DISC_PK = '0db0d16e-8c98-48a5-8ef4-38a86579a4b2'


@override_settings(
    TALOS_GATEWAY={
        'default_identity_disc': THALAMUS_DISC_PK,
        'session_timeout_minutes': 60,
    }
)
class SessionManagerTests(CommonFixturesAPITestCase):
    """Database-backed tests for SessionManager."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    def test_resolve_creates_gateway_and_reasoning_session(self):
        """Assert new channel creates GatewaySession and ReasoningSession."""
        ts = timezone.now()
        env = PlatformEnvelope(
            platform='cli',
            channel_id='chan-sm-1',
            sender_id='u1',
            sender_name='User',
            message_id='m1',
            content='hello',
            timestamp=ts,
        )
        sm = SessionManager()
        gs, rs = sm.resolve_session('cli', 'chan-sm-1', env)
        self.assertEqual(gs.platform, 'cli')
        self.assertEqual(gs.channel_id, 'chan-sm-1')
        self.assertEqual(rs.pk, gs.reasoning_session_id)
        self.assertEqual(str(rs.identity_disc_id), THALAMUS_DISC_PK)

    def test_resolve_reuses_active_session(self):
        """Assert same channel reuses session before timeout."""
        ts = timezone.now()
        env = PlatformEnvelope(
            platform='cli',
            channel_id='chan-sm-2',
            sender_id='u',
            sender_name='User',
            message_id='m1',
            content='a',
            timestamp=ts,
        )
        sm = SessionManager()
        gs1, rs1 = sm.resolve_session('cli', 'chan-sm-2', env)
        gs2, rs2 = sm.resolve_session('cli', 'chan-sm-2', env)
        self.assertEqual(gs1.pk, gs2.pk)
        self.assertEqual(rs1.pk, rs2.pk)

    def test_resolve_rotates_after_timeout(self):
        """Assert stale last_activity yields a new ReasoningSession."""
        ts = timezone.now()
        env = PlatformEnvelope(
            platform='cli',
            channel_id='chan-sm-3',
            sender_id='u',
            sender_name='User',
            message_id='m1',
            content='a',
            timestamp=ts,
        )
        sm = SessionManager()
        gs, rs_old = sm.resolve_session('cli', 'chan-sm-3', env)
        old_pk = rs_old.pk
        GatewaySession.objects.filter(pk=gs.pk).update(
            last_activity=timezone.now() - timedelta(minutes=120)
        )
        _, rs_new = sm.resolve_session('cli', 'chan-sm-3', env)
        self.assertNotEqual(rs_new.pk, old_pk)
        self.assertEqual(ReasoningSession.objects.filter(pk=old_pk).count(), 1)

    def test_list_sessions_returns_active_cli_sessions(self):
        """Assert list_sessions returns dicts with expected fields for active CLI sessions."""
        sm = SessionManager()
        gs, rs = sm.create_session('cli', 'chan-list-1')
        results = sm.list_sessions('cli')
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row['session_id'], str(rs.pk))
        self.assertEqual(row['channel_id'], 'chan-list-1')
        self.assertIn('status', row)
        self.assertIn('last_activity', row)
        self.assertIn('identity_disc_name', row)

    def test_list_sessions_excludes_other_platforms(self):
        """Assert list_sessions for cli excludes discord sessions."""
        sm = SessionManager()
        sm.create_session('cli', 'chan-list-cli')
        sm.create_session('discord', 'chan-list-disc')
        results = sm.list_sessions('cli')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['channel_id'], 'chan-list-cli')

    def test_list_sessions_empty_when_none_exist(self):
        """Assert list_sessions returns empty list when no sessions exist."""
        sm = SessionManager()
        results = sm.list_sessions('cli')
        self.assertEqual(results, [])

    def test_envelope_identity_disc_id_used_for_new_session(self):
        """Assert envelope.identity_disc_id pins identity on a fresh session."""
        ts = timezone.now()
        env = PlatformEnvelope(
            platform='cli',
            channel_id='chan-sm-id-1',
            sender_id='u',
            sender_name='User',
            message_id='m1',
            content='hi',
            identity_disc_id=ALT_DISC_PK,
            timestamp=ts,
        )
        sm = SessionManager()
        _, rs = sm.resolve_session('cli', 'chan-sm-id-1', env)
        self.assertEqual(str(rs.identity_disc_id), ALT_DISC_PK)

    def test_envelope_identity_used_after_timeout_rotation(self):
        """Assert envelope.identity_disc_id wins on post-timeout rotation."""
        ts = timezone.now()
        env_initial = PlatformEnvelope(
            platform='cli',
            channel_id='chan-sm-id-2',
            sender_id='u',
            sender_name='User',
            message_id='m1',
            content='a',
            timestamp=ts,
        )
        sm = SessionManager()
        gs, rs_old = sm.resolve_session('cli', 'chan-sm-id-2', env_initial)
        self.assertEqual(str(rs_old.identity_disc_id), THALAMUS_DISC_PK)

        GatewaySession.objects.filter(pk=gs.pk).update(
            last_activity=timezone.now() - timedelta(minutes=120)
        )
        env_rotate = PlatformEnvelope(
            platform='cli',
            channel_id='chan-sm-id-2',
            sender_id='u',
            sender_name='User',
            message_id='m2',
            content='b',
            identity_disc_id=ALT_DISC_PK,
            timestamp=timezone.now(),
        )
        _, rs_new = sm.resolve_session('cli', 'chan-sm-id-2', env_rotate)
        self.assertNotEqual(rs_new.pk, rs_old.pk)
        self.assertEqual(str(rs_new.identity_disc_id), ALT_DISC_PK)

    def test_envelope_identity_ignored_when_session_still_live(self):
        """Assert live session keeps original identity even if envelope changes it."""
        ts = timezone.now()
        env_initial = PlatformEnvelope(
            platform='cli',
            channel_id='chan-sm-id-3',
            sender_id='u',
            sender_name='User',
            message_id='m1',
            content='a',
            timestamp=ts,
        )
        sm = SessionManager()
        _, rs_first = sm.resolve_session('cli', 'chan-sm-id-3', env_initial)
        env_second = PlatformEnvelope(
            platform='cli',
            channel_id='chan-sm-id-3',
            sender_id='u',
            sender_name='User',
            message_id='m2',
            content='b',
            identity_disc_id=ALT_DISC_PK,
            timestamp=timezone.now(),
        )
        _, rs_second = sm.resolve_session('cli', 'chan-sm-id-3', env_second)
        self.assertEqual(rs_first.pk, rs_second.pk)
        self.assertEqual(
            str(rs_second.identity_disc_id), THALAMUS_DISC_PK
        )

    def test_create_session_returns_gateway_and_reasoning_session(self):
        """Assert create_session creates both GatewaySession and ReasoningSession."""
        sm = SessionManager()
        gs, rs = sm.create_session('cli', 'chan-create-1')
        self.assertIsInstance(gs, GatewaySession)
        self.assertIsInstance(rs, ReasoningSession)
        self.assertEqual(gs.platform, 'cli')
        self.assertEqual(gs.channel_id, 'chan-create-1')
        self.assertEqual(gs.reasoning_session_id, rs.pk)
        self.assertEqual(str(rs.identity_disc_id), THALAMUS_DISC_PK)
