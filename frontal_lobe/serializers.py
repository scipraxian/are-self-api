from dataclasses import dataclass

from rest_framework import serializers

from common.constants import ALL_FIELDS
from frontal_lobe.models import (
    ChatMessage,
    ChatMessageRole,
    ModelRegistry,
    ReasoningSession,
    ReasoningTurn,
    SessionConclusion,
)
from hippocampus.models import TalosEngram
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


class ModelRegistrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelRegistry
        fields = ALL_FIELDS


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


class ChatMessageRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessageRole
        fields = ALL_FIELDS


class ChatMessageSerializer(serializers.ModelSerializer):
    role = ChatMessageRoleSerializer(read_only=True)

    class Meta:
        model = ChatMessage
        fields = ALL_FIELDS


class ReasoningTurnSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    tool_calls = ToolCallSerializer(many=True, read_only=True)
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ReasoningTurn
        fields = ALL_FIELDS


class TalosEngramSerializer(serializers.ModelSerializer):
    source_turns = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = TalosEngram
        fields = ALL_FIELDS


class SessionConclusionSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)

    class Meta:
        model = SessionConclusion
        fields = ALL_FIELDS


class ReasoningSessionLiteSerializer(serializers.ModelSerializer):
    from identity.serializers import IdentityDiscSerializer

    status_name = serializers.CharField(source='status.name', read_only=True)
    identity_disc_name = serializers.CharField(
        source='identity_disc.name', read_only=True
    )

    class Meta:
        model = ReasoningSession
        fields = ALL_FIELDS


class ReasoningSessionGraphSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    turns = ReasoningTurnSerializer(many=True, read_only=True)
    engrams = TalosEngramSerializer(many=True, read_only=True)
    conclusion = SessionConclusionSerializer(read_only=True)

    current_level = serializers.IntegerField(read_only=True)
    max_focus = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReasoningSession
        fields = ALL_FIELDS


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
