import json
from datetime import timedelta
from typing import Optional

from django.db import models

from common.models import (
    CreatedAndModifiedWithDelta,
    CreatedMixin,
    DefaultFieldsMixin,
    DescriptionMixin,
    ModifiedMixin,
    NameMixin,
    UUIDIdMixin,
)


class ReasoningStatusID:
    PENDING = 1
    ACTIVE = 2
    PAUSED = 3
    COMPLETED = 4
    MAXED_OUT = 5
    ERROR = 6
    ATTENTION_REQUIRED = 7
    STOPPED = 8


class ReasoningStatus(NameMixin, ReasoningStatusID):
    """
    Lookup table for Reasoning States.
    """

    IDs = ReasoningStatusID

    class Meta:
        verbose_name_plural = 'Reasoning Statuses'


class ReasoningStatusMixin(models.Model):
    """Mixin to standardize lifecycle states."""

    status = models.ForeignKey(
        ReasoningStatus,
        on_delete=models.PROTECT,
        default=ReasoningStatusID.PENDING,
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Embedding model name — used by Hippocampus for vector operations.
# Replaces the old ModelRegistry.NOMIC_EMBED_TEXT constant.
# ---------------------------------------------------------------------------
NOMIC_EMBED_TEXT_MODEL = 'nomic-embed-text'


class ReasoningSession(
    UUIDIdMixin, CreatedAndModifiedWithDelta, ReasoningStatusMixin
):
    """
    The record of a reasoning process.
    """

    RELATED_NAME = 'reasoning_session'
    identity_disc = models.ForeignKey(
        'identity.IdentityDisc',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name=RELATED_NAME,
    )
    participant = models.ForeignKey(
        'temporal_lobe.IterationShiftParticipant',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name=RELATED_NAME,
    )
    spike = models.ForeignKey(
        'central_nervous_system.Spike',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=RELATED_NAME,
    )
    max_turns = models.IntegerField(default=100)

    total_xp = models.IntegerField(default=0)
    current_focus = models.IntegerField(default=5)

    # Queued messages from users or other agents during a turn.
    swarm_message_queue = models.JSONField(default=list, blank=True)

    @property
    def current_level(self):
        """Fast Leveling: Every 100 XP is a new level."""
        return (self.total_xp // 100) + 1

    @property
    def max_focus(self):
        """Level 1 = 10. Level 2 = 11. Level 3 = 12."""
        return 10 + int((self.current_level - 1) * 0.5)

    @property
    def current_turn(self):
        return self.turns.last() if self.turns.exists() else None

    def __str__(self):
        return f'Session {self.id} Status: {self.status}'


class ReasoningTurn(
    UUIDIdMixin, CreatedAndModifiedWithDelta, ReasoningStatusMixin
):
    """
    A single 'tick' or step in the reasoning process.
    """

    RELATED_NAME = 'turns'

    session = models.ForeignKey(
        ReasoningSession, on_delete=models.CASCADE, related_name=RELATED_NAME
    )
    turn_number = models.IntegerField()

    last_turn = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True
    )

    model_usage_record = models.ForeignKey(
        'hypothalamus.AIModelProviderUsageRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['turn_number']

    def __str__(self):
        return f'Turn {self.turn_number} (Session: {self.session_id})'

    @property
    def thought_process(self) -> str:
        """Proxy to the ledger for legacy compatibility."""
        if self.model_usage_record and self.model_usage_record.response_payload:
            return self.model_usage_record.response_payload.get('content', '')
        return ''

    @property
    def request_payload(self):
        if self.model_usage_record:
            return self.model_usage_record.request_payload
        return None

    @property
    def response_payload(self):
        if self.model_usage_record:
            return self.model_usage_record.response_payload
        return None

    @property
    def inference_time(self) -> timedelta:
        if self.model_usage_record:
            return self.model_usage_record.query_time or timedelta()
        return timedelta()

    @property
    def was_efficient_last_turn(self) -> bool:
        target_capacity = self.session.current_level * 1000
        last_output_len = (
            len(self.last_turn.thought_process) if self.last_turn else 0
        )
        return last_output_len <= target_capacity

    def apply_efficiency_bonus(self) -> (bool, str):
        return False, ''
        # THIS IS REMOVED UNTIL WE REFACTOR THE EFFICIENCY LOGIC.
        # was_efficient = self.was_efficient_last_turn
        # focus = 1
        # xp = 5
        # if was_efficient:
        #     self.session.current_focus = min(
        #         self.session.max_focus, self.session.current_focus + focus
        #     )
        #     self.session.total_xp += xp
        #
        # efficiency_status = (
        #     f'SUCCESS (+{focus} Focus, +{xp} XP)'
        #     if was_efficient
        #     else 'FAILED (Data footprint too large)'
        # )
        # return was_efficient, efficiency_status


class SessionConclusion(CreatedMixin, ModifiedMixin, ReasoningStatusMixin):
    """The crystallized result of a ReasoningSession."""

    session = models.OneToOneField(
        ReasoningSession, on_delete=models.CASCADE, related_name='conclusion'
    )
    summary = models.TextField()
    reasoning_trace = models.TextField(
        help_text='A high-level summary of the thought process.'
    )

    # Structured analog outcome statements by the llm.
    outcome_status = models.TextField()
    recommended_action = models.TextField()

    # The 'Seed' for the next thought
    next_goal_suggestion = models.TextField(blank=True, null=True)
    system_persona_and_prompt_feedback = models.TextField(blank=True, null=True)

    @property
    def engrams(self):
        return self.session.engram_set.all()
