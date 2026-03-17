from rest_framework import serializers

from common.constants import ALL_FIELDS
from hippocampus.models import TalosEngram, TalosEngramTag


class TalosEngramTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = TalosEngramTag
        fields = ALL_FIELDS


class TalosEngramSerializer(serializers.ModelSerializer):
    class Meta:
        model = TalosEngram
        fields = ALL_FIELDS
