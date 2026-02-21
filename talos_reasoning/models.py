from datetime import timedelta

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


class ModelRegistry(DefaultFieldsMixin, NameMixin, DescriptionMixin):
    """
    Database-driven LLM definition.
    Allows us to switch from 'qwen2.5-coder' to 'gpt-4o' via the Admin panel
    without redeploying code.
    """

    DEFAULT_MODEL_ID = 1
    QUEN3_CODER = 1

    api_variant = models.CharField(max_length=50, default='ollama')
    context_window_size = models.IntegerField(default=32768)
    cost_per_1k_input = models.DecimalField(
        max_digits=10, decimal_places=6, default=0
    )
    cost_per_1k_output = models.DecimalField(
        max_digits=10, decimal_places=6, default=0
    )

    class Meta:
        verbose_name_plural = 'Model Registries'


class ReasoningSession(
    UUIDIdMixin, CreatedAndModifiedWithDelta, ReasoningStatusMixin
):
    """
    The record of a reasoning process.
    """

    RELATED_NAME = 'reasoning_session'

    head = models.ForeignKey(
        'hydra.HydraHead',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=RELATED_NAME,
    )
    max_turns = models.IntegerField(default=100)

    total_xp = models.IntegerField(default=0)
    current_focus = models.IntegerField(default=10)

    @property
    def current_level(self):
        """Fast Leveling: Every 50 XP is a new level."""
        return (self.total_xp // 50) + 1

    @property
    def max_focus(self):
        """Level 1 = 10. Level 2 = 15. Level 3 = 20."""
        return 10 + ((self.current_level - 1) * 5)

    @property
    def focus_regen(self):
        """Level 1 = 0. Level 2 = 1. Level 3 = 2."""
        return max(0, self.current_level - 1)

    def apply_sleep_regeneration(self):
        """Called at the start of a turn to apply passive healing."""
        if self.focus_regen > 0:
            self.current_focus = min(
                self.max_focus, self.current_focus + self.focus_regen
            )
            self.save(update_fields=['current_focus'])

    def __str__(self):
        return f'Session {self.id} Status: {self.status}'


class ReasoningGoal(ReasoningStatusMixin, CreatedMixin, ModifiedMixin):
    """Individual objectives within a session."""

    session = models.ForeignKey(
        ReasoningSession, on_delete=models.CASCADE, related_name='goals'
    )
    achieved = models.BooleanField(default=False)
    rendered_goal = models.TextField(blank=True, default='')

    def __str__(self):
        return f'Goal: {self.rendered_goal[:50]}...'


class ReasoningTurn(CreatedAndModifiedWithDelta, ReasoningStatusMixin):
    """
    A single 'tick' or step in the reasoning process.
    """

    RELATED_NAME = 'turns'

    session = models.ForeignKey(
        ReasoningSession, on_delete=models.CASCADE, related_name=RELATED_NAME
    )
    turn_number = models.IntegerField()

    request_payload = models.JSONField(blank=True, default=dict)
    tokens_input = models.IntegerField(default=0)
    inference_time = models.DurationField(default=timedelta)

    turn_goals = models.ManyToManyField(
        ReasoningGoal, blank=True, related_name=RELATED_NAME
    )
    thought_process = models.TextField(
        help_text='The internal monologue of the AI.'
    )
    tokens_output = models.IntegerField(default=0)

    def __str__(self):
        return f'Turn {self.turn_number} (Session: {self.session_id})'


class SessionConclusion(DefaultFieldsMixin, ReasoningStatusMixin):
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

    @property
    def engrams(self):
        return self.session.talosengram_set.all()
