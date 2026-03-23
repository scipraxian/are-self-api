from dataclasses import dataclass
from typing import List

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


class ThalamusMessageSerializer(serializers.Serializer):
    """Schema for a single chat message."""

    role = serializers.CharField()
    content = serializers.CharField()


@dataclass
class ThalamusMessageListDTO:
    messages: List[ThalamusMessageDTO]


class ThalamusMessageListSerializer(serializers.Serializer):
    """Schema for the full history payload expected by assistant-ui."""

    messages = ThalamusMessageSerializer(many=True)
