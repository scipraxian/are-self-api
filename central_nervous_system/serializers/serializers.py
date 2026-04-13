import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.db.models import Avg
from rest_framework import serializers

from central_nervous_system import constants
from central_nervous_system.models import (
    Axon,
    AxonType,
    CNSDistributionMode,
    CNSStatusID,
    CNSTag,
    Effector,
    EffectorArgumentAssignment,
    EffectorContext,
    EffectorTarget,
    NeuralPathway,
    Neuron,
    NeuronContext,
    Spike,
    SpikeTrain,
)
from central_nervous_system.utils import (
    get_active_environment,
    resolve_environment_context,
)
from common.constants import ALL_FIELDS
from environments.variable_renderer import VariableRenderer

# ==========================================
# PART 1: DTOs (Data Transfer Objects)
# Strict typing mimicking the peripheral_nervous_system pattern
# ==========================================


@dataclass
class ContextMatrixRow:
    key: str
    source: str
    value: str
    display_value: str
    is_readonly: bool


@dataclass
class GraphNodeLayout:
    id: int
    title: str
    x: float
    y: float
    effector_id: Optional[int]
    is_root: bool
    has_override: bool
    invoked_pathway_id: Optional[str] = None


@dataclass
class GraphWireLayout:
    from_node_id: int
    to_node_id: int
    status_id: str


# ==========================================
# PART 2: Core Helpers
# ==========================================


def _get_wire_status_label(type_id: int) -> str:
    mapping = {
        AxonType.TYPE_FLOW: constants.TYPE_FLOW_STR,
        AxonType.TYPE_SUCCESS: constants.TYPE_SUCCESS_STR,
        AxonType.TYPE_FAILURE: constants.TYPE_FAIL_STR,
    }
    return mapping.get(type_id, constants.TYPE_FLOW_STR)


def _tail_log(text: Optional[str]) -> str:
    if not text:
        return ''
    lines = text.splitlines()
    tail = lines[-20:] if len(lines) > 20 else lines
    return '\n'.join(tail)


def _get_ui_data(json_str: str) -> Dict[str, int]:
    try:
        return json.loads(json_str)
    except (ValueError, TypeError):
        return {constants.KEY_X: 100, constants.KEY_Y: 100}


def _extract_variables_from_spell(effector: Optional[Effector]) -> set:
    variables = set()
    if not effector:
        return variables
    for a in effector.effectorargumentassignment_set.all():
        found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
        variables.update(found)
    for s in effector.switches.all():
        raw = s.flag + (s.value or '')
        found = re.findall(r'\{\{\s*(\w+)\s*\}\}', raw)
        variables.update(found)
    for (
        a
    ) in effector.executable.executableargumentassignment_set.all():
        found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
        variables.update(found)
    return variables


def _build_context_matrix_data(
    effector: Optional[Effector],
    global_context: Dict[str, Any],
    node_overrides: Dict[str, Any],
) -> List[ContextMatrixRow]:
    variables = _extract_variables_from_spell(effector)
    variables.update(node_overrides.keys())
    matrix = []

    for var in sorted(list(variables)):
        source = 'default'
        value = ''
        display_value = ''
        is_readonly = False

        if var in node_overrides:
            source = 'override'
            value = node_overrides[var]
            display_value = node_overrides[var]
        elif var in global_context:
            source = 'global'
            value = global_context[var]
            display_value = str(global_context[var])
            is_readonly = True

        matrix.append(
            ContextMatrixRow(
                key=var,
                source=source,
                value=value,
                display_value=display_value,
                is_readonly=is_readonly,
            )
        )
    return matrix


# ==========================================
# PART 3: Non-Model Serializers (For DTOs)
# ==========================================


class ContextMatrixRowSerializer(serializers.Serializer):
    """Explicit schema for the Smart Context Matrix."""

    key = serializers.CharField()
    source = serializers.CharField()
    value = serializers.CharField(allow_blank=True)
    display_value = serializers.CharField(allow_blank=True)
    is_readonly = serializers.BooleanField()


class GraphNodeLayoutSerializer(serializers.Serializer):
    """Explicit schema for a Node on the Canvas."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    x = serializers.FloatField()
    y = serializers.FloatField()
    effector_id = serializers.IntegerField(allow_null=True, required=False)
    is_root = serializers.BooleanField()
    has_override = serializers.BooleanField()
    invoked_pathway_id = serializers.UUIDField(allow_null=True, required=False)


class GraphWireLayoutSerializer(serializers.Serializer):
    """Explicit schema for a Wire on the Canvas."""

    from_node_id = serializers.IntegerField()
    to_node_id = serializers.IntegerField()
    status_id = serializers.CharField()


# ==========================================
# PART 4: Model Serializers
# ==========================================


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    A ModelSerializer that takes an additional `fields` query parameter that
    controls which fields should be returned.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get('request')
        if request:
            fields = request.query_params.get('fields')
            if fields:
                fields = fields.split(',')
                allowed = set(fields)
                existing = set(self.fields.keys())
                for field_name in existing - allowed:
                    self.fields.pop(field_name)


class SpikeTrainLightSerializer(DynamicFieldsModelSerializer):
    """
    Ultra-lightweight serializer for list views.
    Drops massive context_data blocks.
    """

    status_name = serializers.CharField(source='status.name', read_only=True)
    pathway_name = serializers.CharField(source='pathway.name', read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = SpikeTrain
        fields = [
            'id',
            'status_name',
            'pathway',
            'pathway_name',
            'parent_spike',
            'created',
            'modified',
            'is_active',
        ]


class SpikeTrainSerializer(DynamicFieldsModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    pathway_name = serializers.CharField(source='pathway.name', read_only=True)
    environment_name = serializers.CharField(
        source='environment.name', read_only=True
    )

    class Meta:
        model = SpikeTrain
        fields = ALL_FIELDS


class CNSTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CNSTag
        fields = ALL_FIELDS


class CNSDistributionModeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CNSDistributionMode
        fields = ALL_FIELDS


class EffectorContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = EffectorContext
        fields = ALL_FIELDS


class EffectorTargetSerializer(serializers.ModelSerializer):
    target_name = serializers.CharField(
        source='target.hostname', read_only=True
    )

    class Meta:
        model = EffectorTarget
        fields = ALL_FIELDS


class EffectorArgumentAssignmentSerializer(serializers.ModelSerializer):
    argument_name = serializers.CharField(
        source='argument.argument', read_only=True
    )

    class Meta:
        model = EffectorArgumentAssignment
        fields = ALL_FIELDS


class EffectorSerializer(serializers.ModelSerializer):
    tags = CNSTagSerializer(many=True, read_only=True)
    executable_name = serializers.CharField(
        source='executable.name', read_only=True
    )
    rendered_command = serializers.SerializerMethodField()
    args = EffectorArgumentAssignmentSerializer(
        source='effectorargumentassignment_set', many=True, read_only=True
    )
    targets = EffectorTargetSerializer(
        source='specific_targets', many=True, read_only=True
    )

    class Meta:
        model = Effector
        fields = ALL_FIELDS

    def get_rendered_command(self, obj) -> str:
        env = self.context.get(constants.ENVIRONMENT_KEY)
        cmd_list = obj.get_full_command(environment=env)
        return ' '.join(cmd_list)


class EffectorBookNodeContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = NeuronContext
        fields = ALL_FIELDS


class CNSNeuralPathwayConnectionWireSerializer(serializers.ModelSerializer):
    type_name = serializers.CharField(source='type.name', read_only=True)
    status_id = serializers.SerializerMethodField()

    class Meta:
        model = Axon
        fields = ALL_FIELDS

    def get_status_id(self, obj):
        return _get_wire_status_label(obj.type_id)

    def validate(self, data):
        pathway = data.get('pathway')
        source = data.get('source')
        target = data.get('target')
        if pathway and source and source.pathway != pathway:
            raise serializers.ValidationError(
                'Source node does not belong to this pathway.'
            )
        if pathway and target and target.pathway != pathway:
            raise serializers.ValidationError(
                'Target node does not belong to this pathway.'
            )
        return data


class CNSNeuralPathwayNodeSerializer(serializers.ModelSerializer):
    effector_name = serializers.CharField(
        source='effector.name', read_only=True
    )
    invoked_pathway_name = serializers.CharField(
        source='invoked_pathway.name', read_only=True
    )
    ui_json = serializers.JSONField(initial=dict)
    has_override = serializers.SerializerMethodField()
    context_overrides = EffectorBookNodeContextSerializer(
        source='neuroncontext_set', many=True, read_only=True
    )

    class Meta:
        model = Neuron
        fields = ALL_FIELDS

    def get_has_override(self, obj):
        return obj.distribution_mode_id is not None

    def validate_ui_json(self, value):
        if isinstance(value, dict):
            return json.dumps(value)
        return value

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        try:
            ret['ui_json'] = json.loads(instance.ui_json)
        except (TypeError, ValueError):
            ret['ui_json'] = {constants.KEY_X: 0, constants.KEY_Y: 0}
        return ret


class CNSNeuralPathwaySerializer(serializers.ModelSerializer):
    environment_name = serializers.CharField(
        source='environment.name', read_only=True
    )
    node_count = serializers.IntegerField(
        source='neurons.count', read_only=True
    )
    tags = CNSTagSerializer(many=True, read_only=True)

    class Meta:
        model = NeuralPathway
        fields = ALL_FIELDS


class CNSGraphLayoutSerializer(serializers.ModelSerializer):
    """Utilizes strict DTO serializers for generating the graph canvas."""

    neurons = serializers.SerializerMethodField()
    connections = serializers.SerializerMethodField()

    class Meta:
        model = NeuralPathway
        fields = [constants.KEY_ID, 'neurons', 'connections']

    def get_nodes(self, obj):
        dtos = []
        neurons = obj.neurons.select_related(
            'effector', 'invoked_pathway', 'distribution_mode'
        ).all()
        for n in neurons:
            ui = _get_ui_data(n.ui_json)
            is_delegated = bool(n.invoked_pathway_id)
            is_root = (
                n.effector_id == Effector.BEGIN_PLAY
            ) and not is_delegated
            title = (
                n.invoked_pathway.name
                if is_delegated
                else (n.effector.name if n.effector else constants.VAL_UNKNOWN)
            )

            dtos.append(
                GraphNodeLayout(
                    id=n.id,
                    title=title,
                    x=ui.get(constants.KEY_X, 0.0),
                    y=ui.get(constants.KEY_Y, 0.0),
                    effector_id=n.effector_id,
                    is_root=is_root,
                    has_override=n.distribution_mode_id is not None,
                    invoked_pathway_id=str(n.invoked_pathway_id)
                    if is_delegated
                    else None,
                )
            )
        return GraphNodeLayoutSerializer(dtos, many=True).data

    def get_connections(self, obj):
        dtos = []
        for w in obj.axons.all():
            dtos.append(
                GraphWireLayout(
                    from_node_id=w.source_id,
                    to_node_id=w.target_id,
                    status_id=_get_wire_status_label(w.type_id),
                )
            )
        return GraphWireLayoutSerializer(dtos, many=True).data


class NeuronDetailsSerializer(serializers.ModelSerializer):
    """Provides deep context analysis utilizing the explicit Row Serializer."""

    context_matrix = serializers.SerializerMethodField()
    name = serializers.CharField(source='effector.name', read_only=True)
    description = serializers.CharField(
        source='effector.description', read_only=True
    )
    node_id = serializers.UUIDField(source='id', read_only=True)

    class Meta:
        model = Neuron
        fields = [
            'node_id',
            'name',
            'description',
            'distribution_mode',
            'context_matrix',
        ]

    def get_context_matrix(self, obj):
        env = obj.pathway.environment if obj.pathway else None
        global_context = VariableRenderer.extract_variables(env)
        overrides = {c.key: c.value for c in obj.neuroncontext_set.all()}

        dtos = _build_context_matrix_data(
            obj.effector, global_context, overrides
        )
        return ContextMatrixRowSerializer(dtos, many=True).data


class SpikeTrainStatusSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='status.name', read_only=True)
    neurons = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = SpikeTrain
        fields = ['status', 'status_label', 'is_active', 'neurons']

    def get_neurons(self, obj):
        node_status_map = {}
        if obj.pathway:
            begin_play_node = obj.pathway.neurons.filter(
                effector_id=Effector.BEGIN_PLAY
            ).first()
            if begin_play_node:
                node_status_map[str(begin_play_node.id)] = {
                    'status_id': CNSStatusID.SUCCESS,
                    'spike_id': None,
                }
        spikes = (
            obj.spikes.select_related('status')
            .prefetch_related('child_trains')
            .order_by('created')
        )

        for spike in spikes:
            if spike.neuron_id:
                child = spike.child_trains.first()
                child_id = str(child.id) if child else None
                node_status_map[str(spike.neuron_id)] = {
                    'status_id': spike.status_id,
                    'spike_id': str(spike.id),
                    'child_spike_train_id': child_id,
                }
        return node_status_map


class SpikeTrainCreateSerializer(serializers.Serializer):
    pathway_id = serializers.UUIDField()
    environment_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_pathway_id(self, value):
        if not NeuralPathway.objects.filter(id=value).exists():
            raise serializers.ValidationError('NeuralPathway not found.')
        return value


class SpikeSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    target_name = serializers.CharField(
        source='target.hostname', read_only=True
    )
    effector_name = serializers.CharField(
        source='effector.name', read_only=True
    )
    average_delta = serializers.SerializerMethodField()

    class Meta:
        model = Spike
        exclude = ['application_log', 'execution_log']

    def get_average_delta(self, obj):
        return Spike.objects.filter(effector=obj.effector).aggregate(
            Avg('delta')
        )['delta__avg']


class NeuronTelemetrySerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    logs = serializers.SerializerMethodField()
    exec_logs = serializers.SerializerMethodField()
    command = serializers.SerializerMethodField()
    agent = serializers.SerializerMethodField()
    average_delta = serializers.SerializerMethodField()
    axoplasm = serializers.JSONField(read_only=True)
    context_matrix = serializers.SerializerMethodField()
    reasoning_session_id = serializers.SerializerMethodField()

    class Meta:
        model = Spike
        fields = [
            constants.KEY_ID,
            'status',
            'status_name',
            'result_code',
            'agent',
            'logs',
            'exec_logs',
            'command',
            'delta',
            'average_delta',
            'axoplasm',
            'context_matrix',
            'reasoning_session_id',
            'spike_train',
        ]

    def get_agent(self, obj):
        return str(obj.target) if obj.target else constants.VAL_PENDING

    def get_logs(self, obj):
        return _tail_log(obj.application_log)

    def get_exec_logs(self, obj):
        return _tail_log(obj.execution_log)

    def get_command(self, obj) -> str:
        try:
            if not obj.effector:
                return constants.VAL_CMD_NOT_CAPTURED
            env = get_active_environment(obj)
            full_context = resolve_environment_context(spike_id=obj.id)
            cmd_list = obj.effector.get_full_command(
                environment=env, extra_context=full_context
            )
            return ' '.join(cmd_list)
        except Exception as e:
            return f'Error resolving command: {str(e)}'

    def get_average_delta(self, obj):
        return Spike.objects.filter(effector=obj.effector).aggregate(
            Avg('delta')
        )['delta__avg']

    def get_context_matrix(self, obj):
        # Ported from cns_graph.py:
        # 1. Inspect the Effector to find variables
        variables = _extract_variables_from_spell(obj.effector)

        # 2. Get Global Context
        # We try to get from node environment first, then spike_train, then pathway
        env = get_active_environment(obj)
        global_context = VariableRenderer.extract_variables(env)

        # 3. Get Overrides
        overrides = {}
        if obj.neuron:
            overrides = {
                c.key: c.value for c in obj.neuron.neuroncontext_set.all()
            }

        # 4. Build Matrix using helper
        dtos = _build_context_matrix_data(
            obj.effector, global_context, overrides
        )
        return ContextMatrixRowSerializer(dtos, many=True).data

    def get_reasoning_session_id(self, obj):
        session = obj.reasoning_session.first()
        return str(session.id) if session else None


class CNSSwimlaneSerializer(serializers.ModelSerializer):
    """
    Specifically shapes a SpikeTrain and its sub-graphs for the Mission Control UI.
    Completely replaces serialize_spawn_helper.
    """

    live_children = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    subgraphs = serializers.SerializerMethodField()

    # Expose ALL properties defined on the SpikeTrain model
    is_active = serializers.BooleanField(read_only=True)  # legacy
    is_alive = serializers.BooleanField(read_only=True)
    is_dead = serializers.BooleanField(read_only=True)
    is_queued = serializers.BooleanField(read_only=True)
    is_stopping = serializers.BooleanField(read_only=True)
    ended_badly = serializers.BooleanField(read_only=True)
    ended_successfully = serializers.BooleanField(read_only=True)
    pathway_name = serializers.CharField(source='pathway.name', read_only=True)

    class Meta:
        model = SpikeTrain
        fields = [
            'id',
            'status',
            'pathway',
            'pathway_name',
            'created',
            'modified',
            'is_active',
            'is_alive',
            'is_dead',
            'is_queued',
            'is_stopping',
            'ended_badly',
            'ended_successfully',
            'live_children',
            'history',
            'subgraphs',
        ]

    def get_live_children(self, obj):
        spikes = obj.live_spikes.all().order_by('created')
        return SpikeSerializer(spikes, many=True).data

    def get_history(self, obj):
        spikes = obj.finished_spikes.all().order_by('created')
        return SpikeSerializer(spikes, many=True).data

    def get_subgraphs(self, obj):
        # Fetch children spike_trains
        live = list(obj.live_spike_trains)
        finished = list(obj.finished_spike_trains)
        children = live + finished
        children.sort(key=lambda x: x.created if x.created else x.modified)

        # Recursive serialization for nested swimlanes
        return CNSSwimlaneSerializer(children, many=True).data
