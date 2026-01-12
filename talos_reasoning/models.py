from django.db import models
from common.models import CreatedMixin, ModifiedMixin, BigIdMixin, NameMixin, UUIDIdMixin


class ReasoningStatusID:
    PENDING = 1
    ACTIVE = 2
    PAUSED = 3
    COMPLETED = 4
    MAXED_OUT = 5
    ERROR = 6
    ATTENTION_REQUIRED = 7


class ReasoningStatus(BigIdMixin, NameMixin):
    """
    Lookup table for Reasoning States.
    """
    IDs = ReasoningStatusID

    class Meta:
        verbose_name_plural = "Reasoning Statuses"


class ReasoningStatusMixin(models.Model):
    """
    Mixin to standardize lifecycle states.
    """
    status = models.ForeignKey(ReasoningStatus,
                               on_delete=models.PROTECT,
                               default=ReasoningStatusID.PENDING)

    class Meta:
        abstract = True


class ToolDefinition(CreatedMixin, ModifiedMixin, BigIdMixin, NameMixin):
    """
    The Registry for AI Tools.
    """
    system_prompt_context = models.TextField(
        help_text=
        "The exact text injected into the LLM system prompt to explain the tool."
    )
    is_async = models.BooleanField(default=False)
    parameters_schema = models.TextField(
        default=dict, blank=True, help_text="JSON schema for tool parameters.")

    def __str__(self):
        return self.name


class ReasoningSession(UUIDIdMixin, CreatedMixin, ModifiedMixin,
                       ReasoningStatusMixin):
    """
    The record of a reasoning process.
    """
    spawn_link = models.ForeignKey('hydra.HydraSpawn',
                                   on_delete=models.CASCADE,
                                   null=True,
                                   blank=True,
                                   related_name='reasoning_sessions')
    goal = models.TextField()
    rolling_context_summary = models.TextField(blank=True, default='')
    max_turns = models.IntegerField(default=10)

    def __str__(self):
        return f"Session {self.id} Status: {self.status}"


class ReasoningGoal(CreatedMixin, ModifiedMixin, ReasoningStatusMixin):
    """
    Individual objectives within a session.
    """
    session = models.ForeignKey(ReasoningSession,
                                on_delete=models.CASCADE,
                                related_name='goals')
    reasoning_prompt = models.TextField(
        help_text="Specific instruction for this goal.")
    parent_goal = models.ForeignKey('self',
                                    on_delete=models.SET_NULL,
                                    null=True,
                                    blank=True,
                                    related_name='sub_goals')

    def __str__(self):
        return f"Goal: {self.reasoning_prompt[:50]}..."


class ReasoningTurn(CreatedMixin, ModifiedMixin, ReasoningStatusMixin):
    """
    A single 'tick' or step in the reasoning process.
    """
    session = models.ForeignKey(ReasoningSession,
                                on_delete=models.CASCADE,
                                related_name='turns')
    active_goal = models.ForeignKey(ReasoningGoal,
                                    on_delete=models.CASCADE,
                                    related_name='turns')
    turn_number = models.IntegerField()
    input_context_snapshot = models.TextField(
        help_text="What the AI saw at the start of this turn.")
    thought_process = models.TextField(
        help_text="The internal monologue of the AI.")

    def __str__(self):
        return f"Turn {self.turn_number} (Session: {self.session_id})"


class ToolCall(CreatedMixin, ModifiedMixin, ReasoningStatusMixin):
    """
    The execution of a tool during a turn.
    """
    turn = models.ForeignKey(ReasoningTurn,
                             on_delete=models.CASCADE,
                             related_name='tool_calls')
    tool = models.ForeignKey(ToolDefinition, on_delete=models.PROTECT)
    arguments = models.TextField(help_text="JSON payload of arguments.")
    result_payload = models.TextField(blank=True, default='')
    traceback = models.TextField(blank=True,
                                 default='',
                                 help_text="Error details if the tool crashed.")

    def __str__(self):
        return f"ToolCall: {self.tool.name} in Turn {self.turn.turn_number}"


class RelevantEngram(CreatedMixin, ModifiedMixin):
    """
    Facts or memories extracted during reasoning.
    """
    session = models.ForeignKey(ReasoningSession,
                                on_delete=models.CASCADE,
                                related_name='engrams')
    source_turn = models.ForeignKey(ReasoningTurn,
                                    on_delete=models.CASCADE,
                                    related_name='engrams')
    fact = models.TextField()
    memory_hash = models.CharField(max_length=64, db_index=True)
    relevance_score = models.FloatField(default=1.0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Engram ({self.relevance_score}): {self.fact[:50]}..."
