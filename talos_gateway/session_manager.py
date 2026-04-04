"""Maps platform channels to reasoning sessions (Layer 4)."""

import logging
from datetime import timedelta
from typing import Optional, Tuple

from django.conf import settings
from django.utils import timezone

from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from identity.models import IdentityDisc

from talos_gateway.contracts import PlatformEnvelope
from talos_gateway.models import GatewaySession, GatewaySessionStatusID

logger = logging.getLogger('talos_gateway.session_manager')


class SessionManager(object):
    """Resolve or create ``GatewaySession`` for a platform channel."""

    def __init__(self, config: Optional[dict] = None) -> None:
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

    def resolve_session(
        self,
        platform: str,
        channel_id: str,
        _envelope: PlatformEnvelope,
    ) -> Tuple[GatewaySession, ReasoningSession]:
        """Return gateway row and its ``ReasoningSession``, creating if needed."""
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
            identity_disc = gs.reasoning_session.identity_disc
            if identity_disc is None:
                identity_disc = self._resolve_identity_disc()
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

        gs.last_activity = timezone.now()
        gs.save(update_fields=['last_activity', 'modified'])
        return gs, gs.reasoning_session
