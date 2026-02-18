from django.db import models

from common.models import (
    DefaultFieldsMixin,
    DescriptionMixin,
    NameMixin,
)
from talos_reasoning.models import ReasoningSession, ReasoningTurn


class TalosEngramTag(NameMixin):
    """A tag for a Talos engram."""


class TalosEngram(DefaultFieldsMixin, DescriptionMixin):
    """A single memory extracted during reasoning.

    args:
        name: A unique hash representing the memory content.
        description: The extracted fact or memory.

        session: The reasoning session this engram belongs to.
        source_turn: The reasoning turn this engram was extracted from.
        is_active: Indicates if the engram is currently active.
    """

    session = models.ForeignKey(
        ReasoningSession, on_delete=models.CASCADE, related_name='engrams'
    )
    source_turn = models.ForeignKey(
        ReasoningTurn, on_delete=models.CASCADE, related_name='engrams'
    )
    heads = models.ManyToManyField(
        'talos_agent.HydraHead', related_name='engrams'
    )
    tags = models.ManyToManyField(TalosEngramTag, related_name='engrams')
    is_active = models.BooleanField(default=True)
