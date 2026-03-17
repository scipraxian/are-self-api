from dataclasses import dataclass

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