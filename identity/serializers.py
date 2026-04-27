from rest_framework import serializers

from common.constants import ALL_FIELDS
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatus,
    ReasoningTurn,
)
from parietal_lobe.models import ToolDefinition

from hypothalamus.models import AIModelSelectionFilter
from neuroplasticity.serializer_mixins import (
    GenomeDisplayMixin,
    GenomeOwnedSerializerMixin,
)

from .models import (
    BudgetPeriod,
    Identity,
    IdentityAddon,
    IdentityBudget,
    IdentityBudgetAssignment,
    IdentityDisc,
    IdentityTag,
    IdentityType,
)


class ToolDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolDefinition
        fields = ALL_FIELDS


class IdentityAddonSerializer(
    GenomeOwnedSerializerMixin, GenomeDisplayMixin, serializers.ModelSerializer
):
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


class SelectionFilterRefSerializer(serializers.ModelSerializer):
    """Lightweight read-only serializer for SelectionFilter FK references."""

    class Meta:
        model = AIModelSelectionFilter
        fields = ('id', 'name')


class IdentityBudgetRefSerializer(serializers.ModelSerializer):
    """Lightweight read-only serializer for IdentityBudget FK references."""

    class Meta:
        model = IdentityBudget
        fields = ('id', 'name')


class IdentitySerializer(
    GenomeOwnedSerializerMixin, GenomeDisplayMixin, serializers.ModelSerializer
):
    enabled_tools = ToolDefinitionSerializer(many=True, read_only=True)
    enabled_tool_ids = serializers.PrimaryKeyRelatedField(
        source='enabled_tools', queryset=ToolDefinition.objects.all(),
        many=True, write_only=True, required=False,
    )
    tags = IdentityTagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        source='tags', queryset=IdentityTag.objects.all(),
        many=True, write_only=True, required=False,
    )
    addons = IdentityAddonSerializer(many=True, read_only=True)
    addon_ids = serializers.PrimaryKeyRelatedField(
        source='addons', queryset=IdentityAddon.objects.all(),
        many=True, write_only=True, required=False,
    )
    identity_type = IdentityTypeSerializer(read_only=True)
    selection_filter = SelectionFilterRefSerializer(read_only=True)
    selection_filter_id = serializers.PrimaryKeyRelatedField(
        source='selection_filter',
        queryset=AIModelSelectionFilter.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    rendered = serializers.SerializerMethodField()

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
            'inference_time',
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


class IdentityDiscSerializer(
    GenomeOwnedSerializerMixin, GenomeDisplayMixin, serializers.ModelSerializer
):
    enabled_tools = ToolDefinitionSerializer(many=True, read_only=True)
    enabled_tool_ids = serializers.PrimaryKeyRelatedField(
        source='enabled_tools', queryset=ToolDefinition.objects.all(),
        many=True, write_only=True, required=False,
    )
    tags = IdentityTagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        source='tags', queryset=IdentityTag.objects.all(),
        many=True, write_only=True, required=False,
    )
    addons = IdentityAddonSerializer(many=True, read_only=True)
    addon_ids = serializers.PrimaryKeyRelatedField(
        source='addons', queryset=IdentityAddon.objects.all(),
        many=True, write_only=True, required=False,
    )
    identity_type = IdentityTypeSerializer(read_only=True)
    selection_filter = SelectionFilterRefSerializer(read_only=True)
    selection_filter_id = serializers.PrimaryKeyRelatedField(
        source='selection_filter',
        queryset=AIModelSelectionFilter.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    budget = IdentityBudgetRefSerializer(read_only=True)
    budget_id = serializers.SerializerMethodField()
    budget_id_write = serializers.PrimaryKeyRelatedField(
        source='budget',
        queryset=IdentityBudget.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    rendered = serializers.SerializerMethodField()
    reasoning_session = IdentityDiscReasoningSerializer(
        read_only=True, many=True
    )
    session_count = serializers.SerializerMethodField()
    turn_count = serializers.SerializerMethodField()

    memories = serializers.SerializerMethodField()

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

    def get_memories(self, identity_disc):
        from frontal_lobe.serializers import (
            EngramSerializer,
        )

        return EngramSerializer(
            identity_disc.engrams.distinct(),
            many=True,
        ).data

    def get_budget_id(self, obj):
        """Get the budget ID from the OneToOne budget_assignments relationship."""
        try:
            assignment = obj.budget_assignments
            if assignment.is_active:
                return assignment.budget_id
            return None
        except IdentityBudgetAssignment.DoesNotExist:
            return None

    def update(self, instance, validated_data):
        """Handle budget assignment when budget_id_write is provided."""
        budget = validated_data.pop('budget', None)

        instance = super().update(instance, validated_data)

        # Handle budget assignment (OneToOne — update or create)
        if budget is not None:
            IdentityBudgetAssignment.objects.update_or_create(
                identity_disc=instance,
                defaults={
                    'budget': budget,
                    'is_active': True,
                },
            )

        return instance


class BudgetPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetPeriod
        fields = ALL_FIELDS


class IdentityBudgetSerializer(serializers.ModelSerializer):
    period = BudgetPeriodSerializer(read_only=True)
    period_id = serializers.PrimaryKeyRelatedField(
        source='period',
        queryset=BudgetPeriod.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = IdentityBudget
        fields = ALL_FIELDS
