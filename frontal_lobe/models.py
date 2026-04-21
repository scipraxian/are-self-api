from datetime import timedelta

from django.db import models

from common.models import (
    BigIdMixin,
    CreatedAndModifiedWithDelta,
    CreatedMixin,
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
    INTERRUPTED = 9


class ReasoningTurnKindID:
    """Lookup IDs for ReasoningTurn.turn_kind (context compression audit)."""

    NORMAL = 1
    SUMMARY = 2


class ReasoningTurnKind(BigIdMixin, NameMixin, ReasoningTurnKindID):
    """Classifies turns for Layer 2 compression (e.g. LLM summary rows)."""

    IDs = ReasoningTurnKindID

    class Meta:
        verbose_name_plural = 'Reasoning Turn Kinds'


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
    current_focus = models.IntegerField(default=10)

    # Queued messages from users or other agents during a turn.
    swarm_message_queue = models.JSONField(default=list, blank=True)

    # Layer 2 interrupt: partial assistant text and metadata when Spike is STOPPING.
    interrupt_snapshot = models.JSONField(default=dict, blank=True)

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

    turn_kind = models.ForeignKey(
        ReasoningTurnKind,
        on_delete=models.PROTECT,
        default=ReasoningTurnKindID.NORMAL,
    )
    is_compressed = models.BooleanField(default=False)

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

    def apply_efficiency_bonus(self) -> tuple[bool, str]:
        """Award Focus and XP when the previous turn's output was concise.

        Conciseness threshold: current_level * 1000 characters.
        Only meaningful when the Focus Addon is attached — otherwise
        this method is never called.
        """
        if not self.last_turn:
            return False, ''

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


class ReasoningTurnDigest(CreatedAndModifiedWithDelta):
    """
    Lightweight summary of a single ReasoningTurn, written at turn close.

    The full request/response payloads and full tool-call bodies stay on
    the ReasoningTurn row and its ModelUsageRecord. The digest holds only
    what the frontend needs to render a node on the reasoning-session
    graph and the turn-level list — enough to show shape, status, tool
    surface, and a short excerpt, without ever shipping a full payload in
    the list response.

    Full payloads are fetched on explicit click via
    /api/v2/reasoning_turns/{id}/.

    Written by a post_save signal on ReasoningTurn when
    model_usage_record is populated (i.e., the assistant message and
    tool_calls are finalized). Discardable and recomputable — no
    authoritative data lives here.

    The digest uses the turn's UUID as its own primary key (side-car
    pattern): one digest per turn, lifecycle tied to turn via CASCADE,
    no orphans possible.
    """

    turn = models.OneToOneField(
        ReasoningTurn,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name='digest',
        help_text='The turn this digest summarizes; also the digest PK.',
    )
    session = models.ForeignKey(
        ReasoningSession,
        on_delete=models.CASCADE,
        related_name='turn_digests',
        db_index=True,
        help_text=(
            'Denormalized from turn.session so the incremental-load '
            'endpoint (graph_data?since_turn_number=N) can filter '
            'digests without joining through ReasoningTurn.'
        ),
    )
    turn_number = models.IntegerField(
        db_index=True,
        help_text='Denormalized from turn.turn_number for cheap ordering.',
    )
    status_name = models.CharField(
        max_length=64,
        db_index=True,
        help_text=(
            'Denormalized ReasoningStatus.name at the time the digest '
            'was written. Read-only shadow; the turn is still the '
            'source of truth.'
        ),
    )
    model_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text=(
            'Flattened from '
            'turn.model_usage_record.ai_model_provider.ai_model.name. '
            'Used to render "qwen2.5-coder:32b" in the turn chip without '
            'traversing four FKs.'
        ),
    )
    tokens_in = models.IntegerField(
        default=0,
        help_text='Input tokens from the turn ModelUsageRecord.',
    )
    tokens_out = models.IntegerField(
        default=0,
        help_text='Output tokens from the turn ModelUsageRecord.',
    )
    excerpt = models.TextField(
        blank=True,
        default='',
        help_text=(
            'Up to ~300 chars of the assistant thought for this turn, '
            'extracted by the same logic the frontend uses '
            '(extractThoughtFromUsageRecord): plain assistant content, '
            'or the "thought" field from an mcp_respond_to_user tool '
            'call if the assistant spoke through the tool. Truncated '
            'with an ellipsis. Not searchable, not authoritative — if '
            'you need the real content, read the turn.'
        ),
    )
    tool_calls_summary = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'List of {id, tool_name, success, target} dicts summarizing '
            "the turn's ToolCall records. Enough to render the Parietal "
            'Lobe chips. The id is the ToolCall pk (as a string) so the '
            'frontend can look up the full row on the fetched turn by '
            'stable id instead of array index. Args and result_payload '
            'intentionally excluded — fetch the turn detail for those.'
        ),
    )
    engram_ids = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'UUIDs (as strings) of engrams formed or referenced during '
            'this turn. Resolved against the engram endpoint by the '
            'frontend; not a FK/M2M because digests are meant to be '
            'nukable without touching hippocampus.'
        ),
    )

    class Meta:
        ordering = ['session_id', 'turn_number']
        verbose_name = 'reasoning turn digest'
        verbose_name_plural = 'reasoning turn digests'
        indexes = [
            models.Index(
                fields=['session', 'turn_number'],
                name='turn_digest_session_turn_idx',
            ),
        ]

    def __str__(self) -> str:
        return 'Digest(turn=%s, #%s, %s)' % (
            str(self.turn_id)[:8],
            self.turn_number,
            self.status_name,
        )


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
