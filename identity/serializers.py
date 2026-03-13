from rest_framework import serializers

from common.constants import ALL_FIELDS
from frontal_lobe.models import ReasoningSession, ReasoningStatus, ReasoningTurn
from frontal_lobe.serializers import (
    ModelRegistrySerializer,
    TalosEngramSerializer,
)
from hippocampus.models import TalosEngram
from parietal_lobe.models import ToolDefinition

from .models import (
    Identity,
    IdentityAddon,
    IdentityDisc,
    IdentityTag,
    IdentityType,
)


class ToolDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolDefinition
        fields = ALL_FIELDS


class IdentityAddonSerializer(serializers.ModelSerializer):
    class Meta:
        model = IdentityAddon
        fields = ALL_FIELDS


class IdentityTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = IdentityTag
        fields = ALL_FIELDS


class IdentityTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IdentityType
        fields = ALL_FIELDS


class IdentitySerializer(serializers.ModelSerializer):
    enabled_tools = ToolDefinitionSerializer(many=True, read_only=True)
    tags = IdentityTagSerializer(many=True, read_only=True)
    addons = IdentityAddonSerializer(many=True, read_only=True)
    identity_type = IdentityTypeSerializer(read_only=True)

    rendered = serializers.SerializerMethodField()
    ai_model = ModelRegistrySerializer()

    class Meta:
        model = Identity
        fields = ALL_FIELDS

    def get_rendered(self, obj):
        from .identity_prompt import render_base_identity

        return render_base_identity(obj, None, 1)


class IdentityDiscTurnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReasoningTurn
        fields = (
            'id',
            'turn_number',
            'tokens_input',
            'tokens_output',
            'inference_time',
            'thought_process',
        )


class ReasoningStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReasoningStatus
        fields = ALL_FIELDS


class IdentityDiscReasoningSerializer(serializers.ModelSerializer):
    current_turn = IdentityDiscTurnSerializer(read_only=True)
    status = ReasoningStatusSerializer(read_only=True)

    class Meta:
        model = ReasoningSession
        fields = (
            'id',
            'status',
            'spike',
            'max_turns',
            'current_focus',
            'current_level',
            'max_focus',
            'current_turn',
        )


class IdentityDiscSerializer(serializers.ModelSerializer):
    ai_model = ModelRegistrySerializer()
    enabled_tools = ToolDefinitionSerializer(many=True, read_only=True)
    tags = IdentityTagSerializer(many=True, read_only=True)
    addons = IdentityAddonSerializer(many=True, read_only=True)
    identity_type = IdentityTypeSerializer(read_only=True)
    rendered = serializers.SerializerMethodField()
    reasoning_session = IdentityDiscReasoningSerializer(
        read_only=True, many=True
    )
    session_count = serializers.SerializerMethodField()
    turn_count = serializers.SerializerMethodField()
    memories = TalosEngramSerializer(many=True, read_only=True)

    class Meta:
        model = IdentityDisc
        fields = ALL_FIELDS

    def get_rendered(self, obj):
        from .identity_prompt import build_identity_prompt

        return build_identity_prompt(obj, None, 1)

    def get_session_count(self, obj):
        return obj.reasoning_session.count()

    def get_turn_count(self, obj):
        return sum(
            session.turns.count() for session in obj.reasoning_session.all()
        )
