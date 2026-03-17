# --- Corpus Callosum DTOs ---
from dataclasses import dataclass

from rest_framework import serializers


@dataclass
class CorpusCallosumRequestDTO:
    message: str


class CorpusCallosumRequestSerializer(serializers.Serializer):
    """Strict schema for the incoming Corpus Callosum chat bubble reply."""

    message = serializers.CharField(
        allow_blank=True, required=False, default=''
    )


@dataclass
class CorpusCallosumResponseDTO:
    ok: bool
    message: str
    spike_train_id: str


class CorpusCallosumResponseSerializer(serializers.Serializer):
    """Strict schema for the API response."""

    ok = serializers.BooleanField()
    message = serializers.CharField()
    spike_train_id = serializers.UUIDField()
