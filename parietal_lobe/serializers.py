from rest_framework import serializers

from common.constants import ALL_FIELDS
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


class ToolDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolDefinition
        fields = ALL_FIELDS


class ToolParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolParameter
        fields = ALL_FIELDS


class ToolParameterAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolParameterAssignment
        fields = ALL_FIELDS


class ParameterEnumSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParameterEnum
        fields = ALL_FIELDS


class ToolCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolCall
        fields = ALL_FIELDS

