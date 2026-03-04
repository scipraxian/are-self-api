from rest_framework import serializers

from common.constants import ALL_FIELDS
from parietal_lobe.models import ToolDefinition

from .identity_prompt import build_identity_prompt, render_base_identity
from .models import (
    Identity,
    IdentityAddon,
    IdentityDisc,
    IdentityTag,
    IdentityType,
)


class ToolDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolDefinition
        fields = ALL_FIELDS


class IdentityAddonSerializer(serializers.ModelSerializer):
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


class IdentitySerializer(serializers.ModelSerializer):
    enabled_tools = ToolDefinitionSerializer(many=True, read_only=True)
    tags = IdentityTagSerializer(many=True, read_only=True)
    addons = IdentityAddonSerializer(many=True, read_only=True)
    identity_type = IdentityTypeSerializer(read_only=True)

    rendered = serializers.SerializerMethodField()

    class Meta:
        model = Identity
        fields = ALL_FIELDS

    def get_rendered(self, obj):
        return render_base_identity(obj, None, 1)


class IdentityDiscSerializer(serializers.ModelSerializer):
    identity = IdentitySerializer(read_only=True)
    rendered = serializers.SerializerMethodField()

    class Meta:
        model = IdentityDisc
        fields = ALL_FIELDS

    def get_rendered(self, obj):
        return build_identity_prompt(obj, None, 1)
