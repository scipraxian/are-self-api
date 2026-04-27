"""DRF serializers for the NeuralModifier admin surface.

Read-only list + detail for NeuralModifier and its installation logs /
events. Writes go through action endpoints (install / uninstall / enable
/ disable / impact), not through PATCH on the modifier detail — mutating
modifier state through generic serializer writes would bypass the
lifecycle loader and is not safe.
"""

from rest_framework import serializers

from .models import (
    NeuralModifier,
    NeuralModifierInstallationEvent,
    NeuralModifierInstallationLog,
)


class NeuralModifierInstallationEventSerializer(serializers.ModelSerializer):
    event_type_name = serializers.CharField(
        source='event_type.name', read_only=True
    )
    event_type_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = NeuralModifierInstallationEvent
        fields = [
            'id',
            'event_type_id',
            'event_type_name',
            'event_data',
            'created',
        ]


class NeuralModifierInstallationLogSerializer(serializers.ModelSerializer):
    events = NeuralModifierInstallationEventSerializer(many=True, read_only=True)

    class Meta:
        model = NeuralModifierInstallationLog
        fields = [
            'id',
            'installation_manifest',
            'events',
            'created',
        ]


class NeuralModifierSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    status_id = serializers.IntegerField(read_only=True)
    row_count = serializers.SerializerMethodField()
    latest_event = serializers.SerializerMethodField()

    class Meta:
        model = NeuralModifier
        fields = [
            'id',
            'slug',
            'name',
            'version',
            'author',
            'license',
            'manifest_hash',
            'manifest_json',
            'status_id',
            'status_name',
            'row_count',
            'latest_event',
            'created',
            'modified',
        ]

    def get_row_count(self, obj):
        from neuroplasticity import loader
        total = 0
        for model in loader.iter_genome_owned_models():
            total += model.objects.filter(genome=obj).count()
        return total

    def get_latest_event(self, obj):
        log = obj.current_installation()
        if log is None:
            return None
        event = log.events.order_by('-created').first()
        if event is None:
            return None
        return {
            'event_type_id': event.event_type_id,
            'event_type_name': event.event_type.name,
            'created': event.created,
            'event_data': event.event_data,
        }


class NeuralModifierDetailSerializer(NeuralModifierSerializer):
    installation_logs = NeuralModifierInstallationLogSerializer(
        many=True, read_only=True
    )

    class Meta(NeuralModifierSerializer.Meta):
        fields = NeuralModifierSerializer.Meta.fields + ['installation_logs']
