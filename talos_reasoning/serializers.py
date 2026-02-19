from rest_framework import serializers

from talos_hippocampus.models import TalosEngram
from talos_parietal.models import ToolCall, ToolDefinition
from talos_reasoning.models import ReasoningSession, ReasoningTurn


class ToolDefinitionSerializer(serializers.ModelSerializer):

    class Meta:
        model = ToolDefinition
        fields = ['name', 'is_async']


class ToolCallSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source='tool.name', read_only=True)
    tool_is_async = serializers.BooleanField(source='tool.is_async',
                                             read_only=True)

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
        fields = [
            'id',
            'description',
            'relevance_score',
            'is_active',
        ]


class ReasoningSessionSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)

    class Meta:
        model = ReasoningSession
        fields = ['id', 'goal', 'status_name']
