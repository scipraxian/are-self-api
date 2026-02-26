from rest_framework import serializers

from common.constants import ALL_FIELDS
from frontal_lobe.models import (
    ReasoningGoal,
    ReasoningSession,
    ReasoningTurn,
    SessionConclusion,
)
from talos_hippocampus.models import TalosEngram
from talos_parietal.models import ToolCall, ToolDefinition


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


class ReasoningGoalSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)

    class Meta:
        model = ReasoningGoal
        fields = ALL_FIELDS


class ReasoningTurnSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    tool_calls = ToolCallSerializer(many=True, read_only=True)
    turn_goals = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

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


class ReasoningSessionSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    goals = ReasoningGoalSerializer(many=True, read_only=True)
    turns = ReasoningTurnSerializer(many=True, read_only=True)
    engrams = TalosEngramSerializer(many=True, read_only=True)
    conclusion = SessionConclusionSerializer(read_only=True)

    current_level = serializers.IntegerField(read_only=True)
    max_focus = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReasoningSession
        fields = ALL_FIELDS
