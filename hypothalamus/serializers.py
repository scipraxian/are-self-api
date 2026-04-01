from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from rest_framework import serializers

from common.constants import ALL_FIELDS
from identity.serializers import IdentityDiscSerializer

from .models import (
    AIMode,
    AIModel,
    AIModelCapabilities,
    AIModelCategory,
    AIModelFamily,
    AIModelPricing,
    AIModelProvider,
    AIModelProviderUsageRecord,
    AIModelRating,
    AIModelRole,
    AIModelSelectionFilter,
    AIModelSyncLog,
    AIModelTags,
    FailoverStrategy,
    FailoverStrategyStep,
    FailoverType,
    LLMProvider,
    SyncStatus,
)

FALLBACK_MODEL_ID = 'ollama/qwen2.5-coder:8b'


@dataclass(frozen=True)
class ModelSelection:
    """The result of a Hypothalamus routing decision."""

    provider_model_id: str
    ai_model_name: str
    distance: float
    input_cost_per_token: Decimal
    is_fallback: bool = False

    @classmethod
    def fallback(cls) -> 'ModelSelection':
        return cls(
            provider_model_id=FALLBACK_MODEL_ID,
            ai_model_name=FALLBACK_MODEL_ID,
            distance=1.0,
            input_cost_per_token=Decimal('0'),
            is_fallback=True,
        )


@dataclass(frozen=True)
class SyncResult:
    """Summary of a catalog sync run."""

    models_added: int
    providers_added: int
    prices_updated: int
    models_deactivated: int
    status: str
    error: Optional[str] = None


class LLMProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = LLMProvider
        fields = ALL_FIELDS


class AIModelCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModelCategory
        fields = ALL_FIELDS


class AIModeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMode
        fields = ALL_FIELDS


class AIModelFamilySerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModelFamily
        fields = ALL_FIELDS


class AIModelRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModelRole
        fields = ALL_FIELDS


class AIModelCapabilitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModelCapabilities
        fields = ALL_FIELDS


class AIModelTagsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModelTags
        fields = ALL_FIELDS


class AIModelSerializer(serializers.ModelSerializer):
    categories = AIModelCategorySerializer(many=True, read_only=True)
    family = AIModelFamilySerializer(read_only=True)
    roles = AIModelRoleSerializer(many=True, read_only=True)
    capabilities = AIModelCapabilitiesSerializer(many=True, read_only=True)

    class Meta:
        model = AIModel
        fields = ALL_FIELDS


class AIModelProviderSerializer(serializers.ModelSerializer):
    ai_model = AIModelSerializer(read_only=True)
    provider = LLMProviderSerializer(read_only=True)
    mode = AIModeSerializer(read_only=True)

    class Meta:
        model = AIModelProvider
        fields = ALL_FIELDS


class AIModelPricingSerializer(serializers.ModelSerializer):
    model_provider = AIModelProviderSerializer(read_only=True)

    class Meta:
        model = AIModelPricing
        fields = ALL_FIELDS


class AIModelProviderUsageRecordSerializer(serializers.ModelSerializer):
    ai_model_provider = AIModelProviderSerializer(read_only=True)
    ai_model = AIModelSerializer(read_only=True)
    identity_disc = IdentityDiscSerializer(read_only=True)

    class Meta:
        model = AIModelProviderUsageRecord
        fields = ALL_FIELDS


class SyncStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncStatus
        fields = ALL_FIELDS


class AIModelSyncLogSerializer(serializers.ModelSerializer):
    status = SyncStatusSerializer(read_only=True)

    class Meta:
        model = AIModelSyncLog
        fields = ALL_FIELDS


class AIModelRatingSerializer(serializers.ModelSerializer):
    ai_model = AIModelSerializer(read_only=True)

    class Meta:
        model = AIModelRating
        fields = ALL_FIELDS


class FailoverTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FailoverType
        fields = ALL_FIELDS


class FailoverStrategyStepSerializer(serializers.ModelSerializer):
    failover_type = FailoverTypeSerializer(read_only=True)
    failover_type_id = serializers.PrimaryKeyRelatedField(
        source='failover_type',
        queryset=FailoverType.objects.all(),
        write_only=True,
    )

    class Meta:
        model = FailoverStrategyStep
        fields = ALL_FIELDS


class FailoverStrategySerializer(serializers.ModelSerializer):
    steps = FailoverStrategyStepSerializer(many=True, read_only=True)

    class Meta:
        model = FailoverStrategy
        fields = ALL_FIELDS


class AIModelSelectionFilterSerializer(serializers.ModelSerializer):
    failover_strategy = FailoverStrategySerializer(read_only=True)
    failover_strategy_id = serializers.PrimaryKeyRelatedField(
        source='failover_strategy',
        queryset=FailoverStrategy.objects.all(),
        write_only=True,
        required=False,
    )

    preferred_model = AIModelProviderSerializer(read_only=True)
    preferred_model_id = serializers.PrimaryKeyRelatedField(
        source='preferred_model',
        queryset=AIModelProvider.objects.all(),
        write_only=True,
        required=False,
    )

    local_failover = AIModelProviderSerializer(read_only=True)
    local_failover_id = serializers.PrimaryKeyRelatedField(
        source='local_failover',
        queryset=AIModelProvider.objects.all(),
        write_only=True,
        required=False,
    )

    required_capabilities = AIModelCapabilitiesSerializer(
        many=True, read_only=True
    )
    required_capabilities_ids = serializers.PrimaryKeyRelatedField(
        source='required_capabilities',
        queryset=AIModelCapabilities.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )

    banned_providers = LLMProviderSerializer(many=True, read_only=True)
    banned_providers_ids = serializers.PrimaryKeyRelatedField(
        source='banned_providers',
        queryset=LLMProvider.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )

    preferred_categories = AIModelCategorySerializer(
        many=True, read_only=True
    )
    preferred_categories_ids = serializers.PrimaryKeyRelatedField(
        source='preferred_categories',
        queryset=AIModelCategory.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )

    preferred_tags = AIModelTagsSerializer(many=True, read_only=True)
    preferred_tags_ids = serializers.PrimaryKeyRelatedField(
        source='preferred_tags',
        queryset=AIModelTags.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )

    preferred_roles = AIModelRoleSerializer(many=True, read_only=True)
    preferred_roles_ids = serializers.PrimaryKeyRelatedField(
        source='preferred_roles',
        queryset=AIModelRole.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )

    class Meta:
        model = AIModelSelectionFilter
        fields = ALL_FIELDS

