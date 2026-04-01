from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from rest_framework import serializers

from common.constants import ALL_FIELDS
from identity.serializers import IdentityDiscSerializer

from .models import (
    AIMode,
    AIModel,
    AIModelCategory,
    AIModelFamily,
    AIModelPricing,
    AIModelProvider,
    AIModelProviderUsageRecord,
    AIModelRating,
    AIModelSyncLog,
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


class AIModelSerializer(serializers.ModelSerializer):
    categories = AIModelCategorySerializer(many=True, read_only=True)
    family = AIModelFamilySerializer(read_only=True)

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

