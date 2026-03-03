from rest_framework import serializers

from common.constants import ALL_FIELDS
from identity.models import (
    Identity,
    IdentityAddon,
    IdentityDisc,
    IdentityTag,
    IdentityType,
)


class IdentityAddonSerializer(serializers.ModelSerializer):
    """Serializer for IdentityAddon."""

    class Meta:
        model = IdentityAddon
        fields = ALL_FIELDS


class IdentityTagSerializer(serializers.ModelSerializer):
    """Serializer for IdentityTag."""

    class Meta:
        model = IdentityTag
        fields = ALL_FIELDS


class IdentityTypeSerializer(serializers.ModelSerializer):
    """Serializer for IdentityType."""

    class Meta:
        model = IdentityType
        fields = ALL_FIELDS


class IdentitySerializer(serializers.ModelSerializer):
    """Serializer for Identity."""

    class Meta:
        model = Identity
        fields = ALL_FIELDS


class IdentityDiscSerializer(serializers.ModelSerializer):
    """Serializer for IdentityDisc."""

    class Meta:
        model = IdentityDisc
        fields = ALL_FIELDS
