"""Django models for gateway session tracking."""

from django.db import models

from common.constants import STANDARD_CHARFIELD_LENGTH
from common.models import CreatedMixin, ModifiedMixin, NameMixin


class GatewaySessionStatusID(object):
    """Static IDs for GatewaySessionStatus rows."""

    ACTIVE = 1
    CLOSED = 2


class GatewaySessionStatus(NameMixin, GatewaySessionStatusID):
    """Lookup table for gateway session lifecycle."""

    IDs = GatewaySessionStatusID

    class Meta(object):
        """Model metadata."""

        verbose_name_plural = 'Gateway session statuses'


class GatewaySession(CreatedMixin, ModifiedMixin):
    """Maps a platform channel to an active reasoning session."""

    platform = models.CharField(max_length=64, db_index=True)
    channel_id = models.CharField(
        max_length=STANDARD_CHARFIELD_LENGTH, db_index=True
    )
    reasoning_session = models.ForeignKey(
        'frontal_lobe.ReasoningSession',
        on_delete=models.CASCADE,
        related_name='gateway_sessions',
    )
    status = models.ForeignKey(
        GatewaySessionStatus,
        on_delete=models.PROTECT,
        default=GatewaySessionStatusID.ACTIVE,
    )
    last_activity = models.DateTimeField(db_index=True)

    class Meta(object):
        """Model metadata."""

        constraints = [
            models.UniqueConstraint(
                fields=('platform', 'channel_id'),
                name='talos_gateway_gatewaysession_platform_channel_uniq',
            ),
        ]

    def __str__(self) -> str:
        return '%s:%s' % (self.platform, self.channel_id)
