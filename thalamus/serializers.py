from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rest_framework import serializers


@dataclass
class ThalamusRequestDTO:
    message: str


class ThalamusRequestSerializer(serializers.Serializer):
    message = serializers.CharField(required=True, allow_blank=False)


@dataclass
class ThalamusResponseDTO:
    ok: bool
    message: str


class ThalamusResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    message = serializers.CharField()


@dataclass
class ThalamusMessageDTO:
    role: str
    content: str
    # Add the parts array to support assistant-ui ChainOfThought primitives
    parts: Optional[List[Dict[str, Any]]] = field(default=None)


class ThalamusMessageSerializer(serializers.Serializer):
    """Schema for a single chat message."""

    role = serializers.CharField()
    # allow_blank=True ensures DRF doesn't crash if the model ONLY outputs parts
    content = serializers.CharField(allow_blank=True)

    # Allow the arbitrary Vercel AI SDK 'parts' dictionaries to pass through to the frontend
    parts = serializers.ListField(child=serializers.DictField(), required=False)


@dataclass
class ThalamusMessageListDTO:
    messages: List[ThalamusMessageDTO]


class ThalamusMessageListSerializer(serializers.Serializer):
    """Schema for the full history payload expected by assistant-ui."""

    messages = ThalamusMessageSerializer(many=True)


@dataclass
class ThalamusModelInfoDTO:
    model_name: Optional[str]
    context_window: Optional[int]
    current_tokens: Optional[int]


class ThalamusModelInfoSerializer(serializers.Serializer):
    """Schema for the Thalamus identity's configured-model pill.

    All three fields are nullable.  Any unresolved link in the
    configured-model chain
    (``IdentityDisc -> selection_filter -> preferred_model -> ai_model``)
    collapses ``model_name`` and ``context_window`` to null. Likewise,
    the live token-pressure read
    (``standing SpikeTrain -> latest non-STOPPED session -> highest-turn
    ReasoningTurn -> model_usage_record.input_tokens``) collapses
    ``current_tokens`` to null when no turn has run yet.
    """

    model_name = serializers.CharField(allow_null=True, allow_blank=True)
    context_window = serializers.IntegerField(allow_null=True)
    current_tokens = serializers.IntegerField(allow_null=True)
