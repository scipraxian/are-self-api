from dataclasses import dataclass
from typing import List, Optional

from django.db.models import QuerySet
from rest_framework import serializers

from talos_hippocampus.models import TalosEngram
from talos_parietal.models import ToolCall, ToolDefinition
from talos_reasoning.models import ReasoningSession, ReasoningTurn


# --- DTOs (Data Transfer Objects) ---
@dataclass
class CortexContextDTO:
    """Strict contract for the Cortex Situation Room HTML template."""

    session: ReasoningSession
    goals: QuerySet
    turns: QuerySet
    engrams: QuerySet
    is_active: bool


@dataclass
class GraphNodeDTO:
    id: str
    type: str
    label: str
    turn_number: Optional[int] = None
    status: Optional[str] = None
    thought_process: Optional[str] = None
    input_context_snapshot: Optional[str] = None
    is_async: Optional[bool] = None
    description: Optional[str] = None
    relevance: Optional[float] = None
    is_active: Optional[bool] = None


@dataclass
class GraphLinkDTO:
    source: str
    target: str
    type: str
    call_id: Optional[str] = None
    arguments: Optional[str] = None
    result: Optional[str] = None
    traceback: Optional[str] = None


@dataclass
class SessionGraphDTO:
    session: dict
    nodes: List[GraphNodeDTO]
    links: List[GraphLinkDTO]


# --- DRF Serializers ---


class GraphNodeSerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.CharField()
    label = serializers.CharField()
    turn_number = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.CharField(required=False, allow_null=True)
    thought_process = serializers.CharField(required=False, allow_null=True)
    input_context_snapshot = serializers.CharField(
        required=False, allow_null=True
    )
    is_async = serializers.BooleanField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_null=True)
    relevance = serializers.FloatField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, allow_null=True)


class GraphLinkSerializer(serializers.Serializer):
    source = serializers.CharField()
    target = serializers.CharField()
    type = serializers.CharField()
    call_id = serializers.CharField(required=False, allow_null=True)
    arguments = serializers.CharField(required=False, allow_null=True)
    result = serializers.CharField(required=False, allow_null=True)
    traceback = serializers.CharField(required=False, allow_null=True)


class ToolDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolDefinition
        fields = ['name', 'is_async']


class ToolCallSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source='tool.name', read_only=True)
    tool_is_async = serializers.BooleanField(
        source='tool.is_async', read_only=True
    )

    class Meta:
        model = ToolCall
        fields = [
            'call_id',
            'tool_name',
            'tool_is_async',
            'arguments',
            'result_payload',
        ]


class ReasoningTurnSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    tool_calls = ToolCallSerializer(many=True, read_only=True)

    class Meta:
        model = ReasoningTurn
        fields = [
            'id',
            'turn_number',
            'status_name',
            'thought_process',
            'created',
            'tool_calls',
        ]


class TalosEngramSerializer(serializers.ModelSerializer):
    class Meta:
        model = TalosEngram
        fields = ['id', 'description', 'relevance_score', 'is_active']


class ReasoningSessionSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)

    class Meta:
        model = ReasoningSession
        fields = ['id', 'status_name']


class SessionGraphDataSerializer(serializers.Serializer):
    """The master serialization block for the D3 graph."""

    session = ReasoningSessionSerializer()
    nodes = GraphNodeSerializer(many=True)
    links = GraphLinkSerializer(many=True)
