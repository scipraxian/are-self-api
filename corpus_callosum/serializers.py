from dataclasses import dataclass
from typing import List

from rest_framework import serializers


@dataclass
class CorpusCallosumRequestDTO:
    message: str


class CorpusCallosumRequestSerializer(serializers.Serializer):
    message = serializers.CharField(required=True, allow_blank=False)


@dataclass
class CorpusCallosumResponseDTO:
    ok: bool
    message: str


class CorpusCallosumResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    message = serializers.CharField()


@dataclass
class CorpusCallosumMessageDTO:
    role: str
    content: str


class CorpusCallosumMessageSerializer(serializers.Serializer):
    """Schema for a single chat message."""

    role = serializers.CharField()
    content = serializers.CharField()


@dataclass
class CorpusCallosumMessageListDTO:
    messages: List[CorpusCallosumMessageDTO]


class CorpusCallosumMessageListSerializer(serializers.Serializer):
    """Schema for the full history payload expected by assistant-ui."""

    messages = CorpusCallosumMessageSerializer(many=True)
