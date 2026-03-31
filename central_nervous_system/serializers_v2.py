import json

from rest_framework import serializers

from central_nervous_system.models import (
    Axon,
    CNSTag,
    Effector,
    NeuralPathway,
    Neuron,
    Spike,
    SpikeTrain,
)


class CNSTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CNSTag
        fields = ['id', 'name']


class EffectorLightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Effector
        fields = ['id', 'name', 'description', 'distribution_mode']


class AxonSerializer(serializers.ModelSerializer):
    type_name = serializers.CharField(source='type.name', read_only=True)

    class Meta:
        model = Axon
        fields = ['id', 'pathway', 'source', 'target', 'type', 'type_name']


class NeuronSerializer(serializers.ModelSerializer):
    effector_name = serializers.CharField(
        source='effector.name', read_only=True
    )
    invoked_pathway_name = serializers.CharField(
        source='invoked_pathway.name', read_only=True
    )

    class Meta:
        model = Neuron
        fields = [
            'id',
            'pathway',
            'effector',
            'effector_name',
            'invoked_pathway',
            'invoked_pathway_name',
            'ui_json',
            'is_root',
            'distribution_mode',
        ]


class NeuralPathwaySerializer(serializers.ModelSerializer):
    tags = CNSTagSerializer(many=True, read_only=True)

    class Meta:
        model = NeuralPathway
        fields = ['id', 'name', 'description', 'is_favorite', 'tags', 'ui_json']


class NeuralPathwayDetailSerializer(NeuralPathwaySerializer):
    """Used specifically for the CNS Editor graph canvas to load all relationships."""

    neurons = NeuronSerializer(many=True, read_only=True)
    axons = AxonSerializer(many=True, read_only=True)

    class Meta(NeuralPathwaySerializer.Meta):
        fields = NeuralPathwaySerializer.Meta.fields + ['neurons', 'axons']


class SpikeSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    effector_name = serializers.CharField(
        source='effector.name', read_only=True
    )
    target_hostname = serializers.CharField(
        source='target.hostname', read_only=True, default=None
    )
    pathway = serializers.CharField(
        source='neuron.pathway.id', read_only=True, default=None
    )
    invoked_pathway = serializers.CharField(
        source='neuron.invoked_pathway.id', read_only=True, default=None
    )
    provenance_train = serializers.CharField(
        source='provenance.spike_train.id', read_only=True, default=None
    )

    class Meta:
        model = Spike
        fields = [
            'id',
            'status',
            'status_name',
            'neuron',
            'effector',
            'effector_name',
            'created',
            'modified',
            'target_hostname',
            'result_code',
            'spike_train',
            'pathway',
            'invoked_pathway',
            'child_trains',
            'provenance',
            'provenance_train',
        ]


class SpikeDetailSerializer(SpikeSerializer):
    """Heavy forensic payload for right-click inspector panels."""

    class Meta(SpikeSerializer.Meta):
        fields = SpikeSerializer.Meta.fields + [
            'application_log',
            'execution_log',
            'blackboard',
        ]


class SpikeTrainSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    pathway_name = serializers.CharField(source='pathway.name', read_only=True)
    spikes = SpikeSerializer(many=True, read_only=True)

    class Meta:
        model = SpikeTrain
        fields = [
            'id',
            'status',
            'status_name',
            'pathway',
            'pathway_name',
            'created',
            'modified',
            'spikes',
        ]
