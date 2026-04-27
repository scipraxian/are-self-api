from rest_framework import serializers

from common.constants import ALL_FIELDS
from neuroplasticity.serializer_mixins import (
    GenomeDisplayMixin,
    GenomeOwnedSerializerMixin,
)
from .models import (
    ParameterEnum,
    ToolCall,
    ToolDefinition,
    ToolParameter,
    ToolParameterAssignment,
    ToolParameterType,
    ToolUseType,
)


class ToolParameterTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolParameterType
        fields = ALL_FIELDS


class ToolUseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolUseType
        fields = ALL_FIELDS


class ToolDefinitionSerializer(
    GenomeOwnedSerializerMixin, GenomeDisplayMixin, serializers.ModelSerializer
):
    class Meta:
        model = ToolDefinition
        fields = ALL_FIELDS


class ToolParameterSerializer(
    GenomeOwnedSerializerMixin, GenomeDisplayMixin, serializers.ModelSerializer
):
    class Meta:
        model = ToolParameter
        fields = ALL_FIELDS


class ToolParameterAssignmentSerializer(
    GenomeOwnedSerializerMixin, GenomeDisplayMixin, serializers.ModelSerializer
):
    class Meta:
        model = ToolParameterAssignment
        fields = ALL_FIELDS


class ParameterEnumSerializer(
    GenomeOwnedSerializerMixin, GenomeDisplayMixin, serializers.ModelSerializer
):
    class Meta:
        model = ParameterEnum
        fields = ALL_FIELDS


class ToolCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolCall
        fields = ALL_FIELDS

