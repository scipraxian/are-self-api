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

    spawn_link = models.ForeignKey(
        'hydra.HydraSpawn',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='reasoning_sessions',
    )
    goal = models.TextField()
    max_turns = models.IntegerField(default=10)
    rolling_context_summary = models.TextField(
        blank=True, default=''
    )  # DEPRECIATED
    message_history = models.JSONField(
        default=list,
        blank=True,
        help_text='The exact array of message dicts sent to the Chat API.',
    )

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

    session = models.ForeignKey(
        ReasoningSession, on_delete=models.CASCADE, related_name='turns'
    )
    active_goal = models.ForeignKey(
        ReasoningGoal, on_delete=models.CASCADE, related_name='turns'
    )
    turn_number = models.IntegerField()
    input_context_snapshot = models.TextField(
        help_text='What the AI saw at the start of this turn.'
    )
    thought_process = models.TextField(
        help_text='The internal monologue of the AI.'
    )

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
    outcome_status = models.CharField(
        max_length=50
    )  # SUCCESS, FAILURE, NEEDS_CLARIFICATION
    recommended_action = models.CharField(
        max_length=100
    )  # RETRY, ABORT, PROCEED, BRANCH_B

    # The 'Seed' for the next thought
    next_goal_suggestion = models.TextField(blank=True, null=True)

    @property
    def engrams(self):
        return self.session.talosengram_set.all()
