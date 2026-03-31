from rest_framework import serializers

from common.constants import ALL_FIELDS
from hippocampus.models import Engram, EngramTag


class EngramTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = EngramTag
        fields = ALL_FIELDS


class EngramSerializer(serializers.ModelSerializer):
    class Meta:
        model = Engram
        fields = ALL_FIELDS
