from django.db import models

from common.models import (
    DefaultFieldsMixin,
    DescriptionMixin,
    NameMixin,
    UUIDIdMixin,
)
from hydra.models import HydraHead
from frontal_lobe.models import ReasoningSession, ReasoningTurn


class TalosEngramTag(NameMixin):
    """A tag for a Talos engram."""


class TalosEngram(UUIDIdMixin, DefaultFieldsMixin, DescriptionMixin):
    """A single memory extracted during reasoning.

    args:
        name: A unique hash representing the memory content. You would use it to
        look up this memory in the future even if you didn't know you had it.
        description: The extracted fact or memory.

        session: The reasoning session this engram belongs to.
        source_turn: The reasoning turn this engram was extracted from.
        is_active: Indicates if the engram is currently active.
    """

    RELATED_NAME = 'engram'

    sessions = models.ManyToManyField(
        ReasoningSession, related_name=RELATED_NAME, blank=True
    )
    source_turns = models.ManyToManyField(
        ReasoningTurn, related_name=RELATED_NAME, blank=True
    )
    heads = models.ManyToManyField(
        HydraHead, related_name=RELATED_NAME, blank=True
    )
    tags = models.ManyToManyField(
        TalosEngramTag, related_name=RELATED_NAME, blank=True
    )
    is_active = models.BooleanField(default=True)
    relevance_score = models.FloatField(default=0.0)
    vector_id = models.UUIDField(null=True, blank=True)
