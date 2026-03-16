from rest_framework import serializers

from common.constants import ALL_FIELDS
from peripheral_nervous_system.models import (
    NerveTerminalEvent,
    NerveTerminalRegistry,
    NerveTerminalStatus,
    NerveTerminalTelemetry,
)


class NerveTerminalStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = NerveTerminalStatus
        fields = ALL_FIELDS


class NerveTerminalRegistrySerializer(serializers.ModelSerializer):
    status = NerveTerminalStatusSerializer(read_only=True)
    status_id = serializers.PrimaryKeyRelatedField(
        source='status', queryset=NerveTerminalStatus.objects.all(), write_only=True
    )

    class Meta:
        model = NerveTerminalRegistry
        fields = ALL_FIELDS


class NerveTerminalTelemetrySerializer(serializers.ModelSerializer):
    target = NerveTerminalRegistrySerializer(read_only=True)
    target_id = serializers.PrimaryKeyRelatedField(
        source='target', queryset=NerveTerminalRegistry.objects.all(), write_only=True
    )

    class Meta:
        model = NerveTerminalTelemetry
        fields = ALL_FIELDS
        read_only_fields = ('id', 'timestamp')


class NerveTerminalEventSerializer(serializers.ModelSerializer):
    target = NerveTerminalRegistrySerializer(read_only=True)
    target_id = serializers.PrimaryKeyRelatedField(
        source='target', queryset=NerveTerminalRegistry.objects.all(), write_only=True
    )

    class Meta:
        model = NerveTerminalEvent
        fields = ALL_FIELDS
        read_only_fields = ('id', 'timestamp')

