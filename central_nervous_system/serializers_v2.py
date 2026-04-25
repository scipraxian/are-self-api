import json

from rest_framework import serializers

from central_nervous_system.models import (
    Axon,
    CNSDistributionMode,
    CNSTag,
    Effector,
    EffectorArgumentAssignment,
    EffectorContext,
    NeuralPathway,
    Neuron,
    Spike,
    SpikeTrain,
)
from environments.models import ProjectEnvironment
from environments.serializers import (
    ExecutableArgumentSerializer,
    ExecutableSerializer,
    ExecutableSwitchSerializer,
)


class CNSTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CNSTag
        fields = ['id', 'name']


class EffectorLightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Effector
        fields = ['id', 'name', 'description', 'distribution_mode']


class EffectorArgumentAssignmentSerializer(serializers.ModelSerializer):
    argument_detail = ExecutableArgumentSerializer(
        source='argument', read_only=True
    )

    class Meta:
        model = EffectorArgumentAssignment
        fields = ['id', 'effector', 'argument', 'order', 'argument_detail']


class EffectorContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = EffectorContext
        fields = ['id', 'effector', 'key', 'value']


class CNSDistributionModeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CNSDistributionMode
        fields = ['id', 'name', 'description']


class EffectorDetailSerializer(serializers.ModelSerializer):
    """
    Full serializer for the Effector Editor page.
    Includes nested read-only details for executable, switches, arguments, and context.
    """

    distribution_mode_detail = CNSDistributionModeSerializer(
        source='distribution_mode', read_only=True
    )
    executable_detail = ExecutableSerializer(
        source='executable', read_only=True
    )
    switches_detail = ExecutableSwitchSerializer(
        source='switches', many=True, read_only=True
    )
    argument_assignments = EffectorArgumentAssignmentSerializer(
        source='effectorargumentassignment_set',
        many=True,
        read_only=True,
    )
    context_entries = EffectorContextSerializer(
        source='effectorcontext_set',
        many=True,
        read_only=True,
    )
    tags = CNSTagSerializer(many=True, read_only=True)
    rendered_full_command = serializers.SerializerMethodField()

    class Meta:
        model = Effector
        fields = [
            'id',
            'name',
            'description',
            'executable',
            'executable_detail',
            'switches',
            'switches_detail',
            'distribution_mode',
            'distribution_mode_detail',
            'argument_assignments',
            'context_entries',
            'tags',
            'is_favorite',
            'rendered_full_command',
        ]

    def get_rendered_full_command(self, obj) -> list:
        """
        Returns the full command line [executable, arg1, arg2, switch1, ...]
        using Effector.get_full_command() which includes all arguments and switches.
        """
        return obj.get_full_command()


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
        source='invoked_pathway.name', read_only=True, default=None
    )
    environment = serializers.PrimaryKeyRelatedField(
        queryset=ProjectEnvironment.objects.all(),
        allow_null=True,
        required=False
    )
    environment_name = serializers.CharField(
        source='environment.name', read_only=True, default=None
    )
    distribution_mode_name = serializers.CharField(
        source='distribution_mode.name', read_only=True, default=None
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
            'distribution_mode_name',
            'environment',
            'environment_name',
        ]


class NeuralPathwaySerializer(serializers.ModelSerializer):
    tags = CNSTagSerializer(many=True, read_only=True)
    environment = serializers.PrimaryKeyRelatedField(
        queryset=ProjectEnvironment.objects.all(),
        allow_null=True,
        required=False
    )
    environment_name = serializers.CharField(
        source='environment.name', read_only=True, default=None
    )
    # Read-only mirror of the genome FK as the bundle slug, for the
    # BEGIN_PLAY inspector's bundle dropdown. Mutation goes through the
    # cascade endpoint /set-genome/, never directly through PATCH.
    genome_slug = serializers.CharField(
        source='genome.slug', read_only=True, default=None
    )

    class Meta:
        model = NeuralPathway
        fields = [
            'id',
            'name',
            'description',
            'is_favorite',
            'tags',
            'ui_json',
            'environment',
            'environment_name',
            'genome_slug',
        ]


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
            'axoplasm',
        ]


class SpikeMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for dashboard views. No deep relation traversals."""

    status_name = serializers.CharField(source='status.name', read_only=True)
    effector_name = serializers.CharField(
        source='effector.name', read_only=True, default=''
    )

    class Meta:
        model = Spike
        fields = [
            'id',
            'status',
            'status_name',
            'effector_name',
            'created',
            'modified',
            'spike_train',
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
