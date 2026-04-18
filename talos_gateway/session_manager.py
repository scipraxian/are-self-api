"""Maps platform channels to reasoning sessions for gateway orchestrator."""

import logging
from datetime import timedelta
from typing import Any, Optional, Tuple

from django.conf import settings
from django.utils import timezone

from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from identity.models import IdentityDisc
from talos_gateway.contracts import PlatformEnvelope
from talos_gateway.models import GatewaySession, GatewaySessionStatusID

logger = logging.getLogger('talos_gateway.session_manager')


class SessionManager(object):
    """Resolve or create ``GatewaySession`` for a platform channel."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self.config = config or getattr(settings, 'TALOS_GATEWAY', {})

    def _resolve_identity_disc(self) -> IdentityDisc:
        """Pick IdentityDisc from settings or first available fixture row."""
        default_uuid = self.config.get('default_identity_disc')
        if default_uuid is not None:
            return IdentityDisc.objects.get(pk=default_uuid)
        disc = IdentityDisc.objects.filter(available=True).first()
        if disc is None:
            raise IdentityDisc.DoesNotExist(
                'No IdentityDisc available for gateway session.'
            )
        return disc

    def _resolve_identity_for_envelope(
        self, envelope: PlatformEnvelope,
    ) -> IdentityDisc:
        """Use envelope-supplied IdentityDisc if present, else default fallback."""
        if envelope.identity_disc_id:
            return IdentityDisc.objects.get(pk=envelope.identity_disc_id)
        return self._resolve_identity_disc()

    def resolve_session(
        self,
        platform: str,
        channel_id: str,
        envelope: PlatformEnvelope,
    ) -> Tuple[GatewaySession, ReasoningSession]:
        """Return gateway row and reasoning session; create rows when absent.

        Identity is pinned at session-creation: an envelope-supplied
        ``identity_disc_id`` is honored only when a new ``ReasoningSession`` is
        created (genesis or post-timeout rotation). Subsequent inbound
        messages on an existing live gateway session reuse that session's
        original ``identity_disc`` even if the envelope carries a different id.
        """
        timeout_minutes = int(self.config.get('session_timeout_minutes', 60))
        cutoff = timezone.now() - timedelta(minutes=timeout_minutes)

        gs: Optional[GatewaySession] = (
            GatewaySession.objects.filter(
                platform=platform,
                channel_id=channel_id,
            )
            .select_related('reasoning_session')
            .first()
        )

        if gs is not None and gs.last_activity < cutoff:
            identity_disc = self._resolve_identity_for_envelope(envelope)
            new_rs = ReasoningSession.objects.create(
                identity_disc=identity_disc,
                status_id=ReasoningStatusID.PENDING,
            )
            gs.reasoning_session = new_rs
            gs.status_id = GatewaySessionStatusID.ACTIVE
            gs.last_activity = timezone.now()
            gs.save(
                update_fields=[
                    'reasoning_session',
                    'status_id',
                    'last_activity',
                    'modified',
                ]
            )
            logger.info(
                '[SessionManager] Rotated reasoning session for %s:%s after '
                'timeout.',
                platform,
                channel_id,
            )
            return gs, new_rs

        if gs is None:
            identity_disc = self._resolve_identity_for_envelope(envelope)
            rs = ReasoningSession.objects.create(
                identity_disc=identity_disc,
                status_id=ReasoningStatusID.PENDING,
            )
            gs = GatewaySession.objects.create(
                platform=platform,
                channel_id=channel_id,
                reasoning_session=rs,
                status_id=GatewaySessionStatusID.ACTIVE,
                last_activity=timezone.now(),
            )
            return gs, rs

        gs.last_activity = timezone.now()
        gs.save(update_fields=['last_activity', 'modified'])
        return gs, gs.reasoning_session

    def list_sessions(self, platform: str) -> list[dict]:
        """Return active sessions for a platform as serializable dicts."""
        rows = (
            GatewaySession.objects.filter(
                platform=platform,
                status_id=GatewaySessionStatusID.ACTIVE,
            )
            .select_related('reasoning_session', 'reasoning_session__identity_disc')
            .order_by('-last_activity')
        )
        results: list[dict] = []
        for gs in rows:
            rs = gs.reasoning_session
            disc = getattr(rs, 'identity_disc', None)
            results.append({
                'session_id': str(rs.pk),
                'channel_id': gs.channel_id,
                'status': str(gs.status_id),
                'last_activity': gs.last_activity.isoformat(),
                'identity_disc_name': str(disc) if disc else '',
            })
        return results

    def create_session(
        self, platform: str, channel_id: str
    ) -> Tuple[GatewaySession, ReasoningSession]:
        """Create a new gateway + reasoning session pair without an envelope."""
        identity_disc = self._resolve_identity_disc()
        rs = ReasoningSession.objects.create(
            identity_disc=identity_disc,
            status_id=ReasoningStatusID.PENDING,
        )
        gs = GatewaySession.objects.create(
            platform=platform,
            channel_id=channel_id,
            reasoning_session=rs,
            status_id=GatewaySessionStatusID.ACTIVE,
            last_activity=timezone.now(),
        )
        return gs, rs
