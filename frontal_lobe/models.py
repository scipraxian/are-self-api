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
    GEMMA3 = 2
    LLAMA3_LATEST = 3
    LLAMA3 = 4
    NOMIC_EMBED_TEXT = 5

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

    @property
    def current_level(self):
        """Fast Leveling: Every 100 XP is a new level."""
        return (self.total_xp // 100) + 1

    @property
    def max_focus(self):
        """Level 1 = 10. Level 2 = 11. Level 3 = 12."""
        return 10 + int((self.current_level - 1) * 0.5)

    def __str__(self):
        return f'Session {self.id} Status: {self.status}'


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

    thought_process = models.TextField(
        help_text='The internal monologue of the AI.'
    )
    tokens_output = models.IntegerField(default=0)

    last_turn = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f'Turn {self.turn_number} (Session: {self.session_id})'

    @property
    def was_efficient_last_turn(self) -> bool:
        target_capacity = self.session.current_level * 1000
        last_output_len = (
            len(self.last_turn.thought_process)
            if self.last_turn and self.last_turn.thought_process
            else 0
        )
        return last_output_len <= target_capacity

    def apply_efficiency_bonus(self) -> (bool, str):
        was_efficient = self.was_efficient_last_turn
        focus = 1
        xp = 5
        if was_efficient:
            self.session.current_focus = min(
                self.session.max_focus, self.session.current_focus + focus
            )
            self.session.total_xp += xp

        efficiency_status = (
            f'SUCCESS (+{focus} Focus, +{xp} XP)'
            if was_efficient
            else 'FAILED (Data footprint too large)'
        )
        return was_efficient, efficiency_status


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
        return self.session.talosengram_set.all()


class ChatMessageRole(NameMixin, CreatedMixin):
    SYSTEM = 1  #'system', 'System'
    USER = 2  #'user', 'User'
    ASSISTANT = 3  # 'assistant', 'Assistant'
    TOOL = 4


class ChatMessage(UUIDIdMixin, CreatedMixin):
    RELATED_NAME = 'messages'
    session = models.ForeignKey(
        ReasoningSession, on_delete=models.CASCADE, related_name=RELATED_NAME
    )
    turn = models.ForeignKey(
        ReasoningTurn, on_delete=models.CASCADE, related_name=RELATED_NAME
    )
    role = models.ForeignKey(ChatMessageRole, on_delete=models.CASCADE)
    content = models.TextField()
    tool_call = models.ForeignKey(
        'parietal_lobe.ToolCall',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    is_volatile = models.BooleanField(
        default=False,
        help_text='If True, this message (like an Addon) is excluded from historical memory.',
    )

    class Meta:
        ordering = ['-created']
        verbose_name = 'Chat Message'
        verbose_name_plural = 'Chat Messages'
