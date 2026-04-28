from dataclasses import dataclass

from rest_framework import serializers

from common.constants import ALL_FIELDS
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningTurn,
    ReasoningTurnDigest,
    SessionConclusion,
)
from hippocampus.models import Engram
from hypothalamus.serializers import AIModelProviderUsageRecordSerializer
from parietal_lobe.models import ToolCall, ToolDefinition

KEY_REPLY = 'reply'
KEY_OK = 'ok'


@dataclass
class ResumeSessionRequestDTO:
    reply: str


class ResumeSessionRequestSerializer(serializers.Serializer):
    """Strict schema for the incoming human reply."""

    reply = serializers.CharField(allow_blank=True, required=False, default='')


@dataclass
class ResumeSessionResponseDTO:
    ok: bool
    message: str


class ResumeSessionResponseSerializer(serializers.Serializer):
    """Strict schema for the API response."""

    ok = serializers.BooleanField()
    message = serializers.CharField()


class ToolDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolDefinition
        fields = ALL_FIELDS


class ToolCallSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source='tool.name', read_only=True)
    is_async = serializers.BooleanField(source='tool.is_async', read_only=True)

    class Meta:
        model = ToolCall
        fields = ALL_FIELDS


class ReasoningTurnSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    tool_calls = ToolCallSerializer(many=True, read_only=True)
    model_usage_record = AIModelProviderUsageRecordSerializer(read_only=True)

    class Meta:
        model = ReasoningTurn
        fields = ALL_FIELDS


class EngramSerializer(serializers.ModelSerializer):
    source_turns = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Engram
        fields = ALL_FIELDS


class ReasoningSessionLiteSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    identity_disc_name = serializers.CharField(
        source='identity_disc.name', read_only=True
    )

    class Meta:
        model = ReasoningSession
        fields = ALL_FIELDS


class ReasoningSessionMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for dashboard and list views. No heavy relations."""

    status_name = serializers.CharField(source='status.name', read_only=True)
    identity_disc_name = serializers.CharField(
        source='identity_disc.name',
        read_only=True,
        default='Unassigned',
    )
    turns_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReasoningSession
        fields = [
            'id',
            'status',
            'status_name',
            'identity_disc_name',
            'created',
            'modified',
            'turns_count',
        ]


class _IsoformatDateTimeField(serializers.DateTimeField):
    """Serializes datetimes with raw ``isoformat()`` (no Z conversion).

    DRF's default DateTimeField swaps a trailing ``+00:00`` for ``Z``;
    the digest vesicle does not. This subclass keeps the pull transport
    byte-identical to what ``digest_to_vesicle()`` emits on the push
    side, so a round-trip test can assert dict equality.
    """

    def to_representation(self, value):
        if value is None:
            return None
        return value.isoformat()


class SessionConclusionSerializer(serializers.ModelSerializer):
    """Read-only shape for SessionConclusion pull responses.

    Kept key-identical to ``conclusion_to_vesicle()`` in
    ``frontal_lobe.signals`` so the push transport (Acetylcholine vesicle)
    and the pull transport (``/api/v2/reasoning_sessions/{id}/conclusion/``)
    never drift. ``created`` / ``modified`` use ``isoformat()`` via
    ``_IsoformatDateTimeField`` to stay byte-identical to the vesicle.
    """

    session_id = serializers.UUIDField(read_only=True)
    status_name = serializers.CharField(source='status.name', read_only=True)
    created = _IsoformatDateTimeField(read_only=True)
    modified = _IsoformatDateTimeField(read_only=True)

    class Meta:
        model = SessionConclusion
        fields = (
            'id',
            'session_id',
            'status_name',
            'summary',
            'reasoning_trace',
            'outcome_status',
            'recommended_action',
            'next_goal_suggestion',
            'system_persona_and_prompt_feedback',
            'created',
            'modified',
        )
        read_only_fields = fields


class DigestSerializer(serializers.ModelSerializer):
    """Read-only shape for ReasoningTurnDigest pull responses.

    Kept key-identical to ``digest_builder.digest_to_vesicle()`` so the
    push transport (Acetylcholine vesicle) and the pull transport
    (``graph_data?since_turn_number=N``) never drift. ``turn_id`` /
    ``session_id`` go out as UUID strings matching the vesicle; ``created``
    / ``modified`` use ``isoformat()`` via ``_IsoformatDateTimeField``.
    """

    turn_id = serializers.UUIDField(read_only=True)
    session_id = serializers.UUIDField(read_only=True)
    created = _IsoformatDateTimeField(read_only=True)
    modified = _IsoformatDateTimeField(read_only=True)

    class Meta:
        model = ReasoningTurnDigest
        fields = (
            'turn_id',
            'session_id',
            'turn_number',
            'status_name',
            'model_name',
            'tokens_in',
            'tokens_out',
            'excerpt',
            'tool_calls_summary',
            'engram_ids',
            'created',
            'modified',
            'delta',
        )
        read_only_fields = fields


@dataclass
class LLMFunctionCall:
    name: str
    arguments: str  # The LLM API expects this to be a stringified JSON object


@dataclass
class LLMToolCall:
    id: str
    function: LLMFunctionCall
    type: str = 'function'

    def to_dict(self) -> dict:
        """Serializes exactly to the strict LLM schema."""
        return {
            'id': self.id,
            'type': self.type,
            'function': {
                'name': self.function.name,
                'arguments': self.function.arguments,
            },
        }
