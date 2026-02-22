import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.db.models import Avg
from rest_framework import serializers

from common.constants import ALL_FIELDS
from environments.variable_renderer import VariableRenderer
from hydra import constants
from hydra.utils import get_active_environment, resolve_environment_context

from .models import (
    HydraDistributionMode,
    HydraHead,
    HydraSpawn,
    HydraSpell,
    HydraSpellArgumentAssignment,
    HydraSpellbook,
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraSpellBookNodeContext,
    HydraSpellContext,
    HydraSpellTarget,
    HydraStatusID,
    HydraTag,
    HydraWireType,
)

# ==========================================
# PART 1: DTOs (Data Transfer Objects)
# Strict typing mimicking the talos_agent pattern
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
    spell_id: Optional[int]
    is_root: bool
    has_override: bool
    invoked_spellbook_id: Optional[str] = None


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
        HydraWireType.TYPE_FLOW: constants.TYPE_FLOW_STR,
        HydraWireType.TYPE_SUCCESS: constants.TYPE_SUCCESS_STR,
        HydraWireType.TYPE_FAILURE: constants.TYPE_FAIL_STR,
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


def _extract_variables_from_spell(spell: Optional[HydraSpell]) -> set:
    variables = set()
    if not spell:
        return variables
    for a in spell.hydraspellargumentassignment_set.all():
        found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
        variables.update(found)
    for s in spell.switches.all():
        raw = s.flag + (s.value or '')
        found = re.findall(r'\{\{\s*(\w+)\s*\}\}', raw)
        variables.update(found)
    for a in spell.talos_executable.talosexecutableargumentassignment_set.all():
        found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
        variables.update(found)
    return variables


def _build_context_matrix_data(
    spell: Optional[HydraSpell],
    global_context: Dict[str, Any],
    node_overrides: Dict[str, Any],
) -> List[ContextMatrixRow]:
    variables = _extract_variables_from_spell(spell)
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
    spell_id = serializers.IntegerField(allow_null=True, required=False)
    is_root = serializers.BooleanField()
    has_override = serializers.BooleanField()
    invoked_spellbook_id = serializers.UUIDField(
        allow_null=True, required=False
    )


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


class HydraSpawnLightSerializer(DynamicFieldsModelSerializer):
    """
    Ultra-lightweight serializer for list views.
    Drops massive context_data blocks.
    """

    status_name = serializers.CharField(source='status.name', read_only=True)
    spellbook_name = serializers.CharField(
        source='spellbook.name', read_only=True
    )
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = HydraSpawn
        fields = [
            'id',
            'status_name',
            'spellbook',
            'spellbook_name',
            'parent_head',
            'created',
            'modified',
            'is_active',
        ]


class HydraSpawnSerializer(DynamicFieldsModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    spellbook_name = serializers.CharField(
        source='spellbook.name', read_only=True
    )
    environment_name = serializers.CharField(
        source='environment.name', read_only=True
    )

    class Meta:
        model = HydraSpawn
        fields = ALL_FIELDS


class HydraTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = HydraTag
        fields = ALL_FIELDS


class HydraDistributionModeSerializer(serializers.ModelSerializer):
    class Meta:
        model = HydraDistributionMode
        fields = ALL_FIELDS


class HydraSpellContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = HydraSpellContext
        fields = ALL_FIELDS


class HydraSpellTargetSerializer(serializers.ModelSerializer):
    target_name = serializers.CharField(
        source='target.hostname', read_only=True
    )

    class Meta:
        model = HydraSpellTarget
        fields = ALL_FIELDS


class HydraSpellArgumentAssignmentSerializer(serializers.ModelSerializer):
    argument_name = serializers.CharField(
        source='argument.argument', read_only=True
    )

    class Meta:
        model = HydraSpellArgumentAssignment
        fields = ALL_FIELDS


class HydraSpellSerializer(serializers.ModelSerializer):
    tags = HydraTagSerializer(many=True, read_only=True)
    executable_name = serializers.CharField(
        source='talos_executable.name', read_only=True
    )
    rendered_command = serializers.SerializerMethodField()
    args = HydraSpellArgumentAssignmentSerializer(
        source='hydraspellargumentassignment_set', many=True, read_only=True
    )
    targets = HydraSpellTargetSerializer(
        source='specific_targets', many=True, read_only=True
    )

    class Meta:
        model = HydraSpell
        fields = ALL_FIELDS

    def get_rendered_command(self, obj) -> str:
        env = self.context.get(constants.ENVIRONMENT_KEY)
        cmd_list = obj.get_full_command(environment=env)
        return ' '.join(cmd_list)


class HydraSpellBookNodeContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = HydraSpellBookNodeContext
        fields = ALL_FIELDS


class HydraSpellbookConnectionWireSerializer(serializers.ModelSerializer):
    type_name = serializers.CharField(source='type.name', read_only=True)
    status_id = serializers.SerializerMethodField()

    class Meta:
        model = HydraSpellbookConnectionWire
        fields = ALL_FIELDS

    def get_status_id(self, obj):
        return _get_wire_status_label(obj.type_id)

    def validate(self, data):
        spellbook = data.get('spellbook')
        source = data.get('source')
        target = data.get('target')
        if spellbook and source and source.spellbook != spellbook:
            raise serializers.ValidationError(
                'Source node does not belong to this spellbook.'
            )
        if spellbook and target and target.spellbook != spellbook:
            raise serializers.ValidationError(
                'Target node does not belong to this spellbook.'
            )
        return data


class HydraSpellbookNodeSerializer(serializers.ModelSerializer):
    spell_name = serializers.CharField(source='spell.name', read_only=True)
    invoked_spellbook_name = serializers.CharField(
        source='invoked_spellbook.name', read_only=True
    )
    ui_json = serializers.JSONField(initial=dict)
    has_override = serializers.SerializerMethodField()
    context_overrides = HydraSpellBookNodeContextSerializer(
        source='hydraspellbooknodecontext_set', many=True, read_only=True
    )

    class Meta:
        model = HydraSpellbookNode
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


class HydraSpellbookSerializer(serializers.ModelSerializer):
    environment_name = serializers.CharField(
        source='environment.name', read_only=True
    )
    node_count = serializers.IntegerField(source='nodes.count', read_only=True)
    tags = HydraTagSerializer(many=True, read_only=True)

    class Meta:
        model = HydraSpellbook
        fields = ALL_FIELDS


class HydraGraphLayoutSerializer(serializers.ModelSerializer):
    """Utilizes strict DTO serializers for generating the graph canvas."""

    nodes = serializers.SerializerMethodField()
    connections = serializers.SerializerMethodField()

    class Meta:
        model = HydraSpellbook
        fields = [constants.KEY_ID, 'nodes', 'connections']

    def get_nodes(self, obj):
        dtos = []
        nodes = obj.nodes.select_related(
            'spell', 'invoked_spellbook', 'distribution_mode'
        ).all()
        for n in nodes:
            ui = _get_ui_data(n.ui_json)
            is_delegated = bool(n.invoked_spellbook_id)
            is_root = (n.spell_id == HydraSpell.BEGIN_PLAY) and not is_delegated
            title = (
                n.invoked_spellbook.name
                if is_delegated
                else (n.spell.name if n.spell else constants.VAL_UNKNOWN)
            )

            dtos.append(
                GraphNodeLayout(
                    id=n.id,
                    title=title,
                    x=ui.get(constants.KEY_X, 0.0),
                    y=ui.get(constants.KEY_Y, 0.0),
                    spell_id=n.spell_id,
                    is_root=is_root,
                    has_override=n.distribution_mode_id is not None,
                    invoked_spellbook_id=str(n.invoked_spellbook_id)
                    if is_delegated
                    else None,
                )
            )
        return GraphNodeLayoutSerializer(dtos, many=True).data

    def get_connections(self, obj):
        dtos = []
        for w in obj.wires.all():
            dtos.append(
                GraphWireLayout(
                    from_node_id=w.source_id,
                    to_node_id=w.target_id,
                    status_id=_get_wire_status_label(w.type_id),
                )
            )
        return GraphWireLayoutSerializer(dtos, many=True).data


class HydraNodeDetailsSerializer(serializers.ModelSerializer):
    """Provides deep context analysis utilizing the explicit Row Serializer."""

    context_matrix = serializers.SerializerMethodField()
    name = serializers.CharField(source='spell.name', read_only=True)
    description = serializers.CharField(
        source='spell.description', read_only=True
    )
    node_id = serializers.UUIDField(source='id', read_only=True)

    class Meta:
        model = HydraSpellbookNode
        fields = [
            'node_id',
            'name',
            'description',
            'distribution_mode',
            'context_matrix',
        ]

    def get_context_matrix(self, obj):
        env = obj.spellbook.environment if obj.spellbook else None
        global_context = VariableRenderer.extract_variables(env)
        overrides = {
            c.key: c.value for c in obj.hydraspellbooknodecontext_set.all()
        }

        dtos = _build_context_matrix_data(obj.spell, global_context, overrides)
        return ContextMatrixRowSerializer(dtos, many=True).data


class HydraSpawnStatusSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='status.name', read_only=True)
    nodes = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = HydraSpawn
        fields = ['status', 'status_label', 'is_active', 'nodes']

    def get_nodes(self, obj):
        node_status_map = {}
        if obj.spellbook:
            begin_play_node = obj.spellbook.nodes.filter(
                spell_id=HydraSpell.BEGIN_PLAY
            ).first()
            if begin_play_node:
                node_status_map[str(begin_play_node.id)] = {
                    'status_id': HydraStatusID.SUCCESS,
                    'head_id': None,
                }
        heads = (
            obj.heads.select_related('status')
            .prefetch_related('child_spawns')
            .order_by('created')
        )

        for head in heads:
            if head.node_id:
                child = head.child_spawns.first()
                child_id = str(child.id) if child else None
                node_status_map[str(head.node_id)] = {
                    'status_id': head.status_id,
                    'head_id': str(head.id),
                    'child_spawn_id': child_id,
                }
        return node_status_map


class HydraSpawnCreateSerializer(serializers.Serializer):
    spellbook_id = serializers.UUIDField()
    environment_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_spellbook_id(self, value):
        if not HydraSpellbook.objects.filter(id=value).exists():
            raise serializers.ValidationError('Spellbook not found.')
        return value


class HydraHeadSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    target_name = serializers.CharField(
        source='target.hostname', read_only=True
    )
    spell_name = serializers.CharField(source='spell.name', read_only=True)
    average_delta = serializers.SerializerMethodField()

    class Meta:
        model = HydraHead
        exclude = ['spell_log', 'execution_log']

    def get_average_delta(self, obj):
        return HydraHead.objects.filter(spell=obj.spell).aggregate(
            Avg('delta')
        )['delta__avg']


class HydraNodeTelemetrySerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    logs = serializers.SerializerMethodField()
    exec_logs = serializers.SerializerMethodField()
    command = serializers.SerializerMethodField()
    agent = serializers.SerializerMethodField()
    average_delta = serializers.SerializerMethodField()
    blackboard = serializers.JSONField(read_only=True)
    context_matrix = serializers.SerializerMethodField()
    reasoning_session_id = serializers.SerializerMethodField()

    class Meta:
        model = HydraHead
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
            'blackboard',
            'context_matrix',
            'reasoning_session_id',
        ]

    def get_agent(self, obj):
        return str(obj.target) if obj.target else constants.VAL_PENDING

    def get_logs(self, obj):
        return _tail_log(obj.spell_log)

    def get_exec_logs(self, obj):
        return _tail_log(obj.execution_log)

    def get_command(self, obj) -> str:
        try:
            if not obj.spell:
                return constants.VAL_CMD_NOT_CAPTURED
            env = get_active_environment(obj)
            full_context = resolve_environment_context(head_id=obj.id)
            cmd_list = obj.spell.get_full_command(
                environment=env, extra_context=full_context
            )
            return ' '.join(cmd_list)
        except Exception as e:
            return f'Error resolving command: {str(e)}'

    def get_average_delta(self, obj):
        return HydraHead.objects.filter(spell=obj.spell).aggregate(
            Avg('delta')
        )['delta__avg']

    def get_context_matrix(self, obj):
        # Ported from hydra_graph.py:
        # 1. Inspect the Spell to find variables
        variables = _extract_variables_from_spell(obj.spell)

        # 2. Get Global Context
        # We try to get from node environment first, then spawn, then spellbook
        env = get_active_environment(obj)
        global_context = VariableRenderer.extract_variables(env)

        # 3. Get Overrides
        overrides = {}
        if obj.node:
            overrides = {
                c.key: c.value
                for c in obj.node.hydraspellbooknodecontext_set.all()
            }

        # 4. Build Matrix using helper
        dtos = _build_context_matrix_data(obj.spell, global_context, overrides)
        return ContextMatrixRowSerializer(dtos, many=True).data

    def get_reasoning_session_id(self, obj):
        session = obj.reasoning_session.first()
        return str(session.id) if session else None


class HydraSwimlaneSerializer(serializers.ModelSerializer):
    """
    Specifically shapes a Spawn and its sub-graphs for the Mission Control UI.
    Completely replaces serialize_spawn_helper.
    """

    live_children = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    subgraphs = serializers.SerializerMethodField()

    # Expose ALL properties defined on the HydraSpawn model
    is_active = serializers.BooleanField(read_only=True)  # legacy
    is_alive = serializers.BooleanField(read_only=True)
    is_dead = serializers.BooleanField(read_only=True)
    is_queued = serializers.BooleanField(read_only=True)
    is_stopping = serializers.BooleanField(read_only=True)
    ended_badly = serializers.BooleanField(read_only=True)
    ended_successfully = serializers.BooleanField(read_only=True)
    spellbook_name = serializers.CharField(
        source='spellbook.name', read_only=True
    )

    class Meta:
        model = HydraSpawn
        fields = [
            'id',
            'status',
            'spellbook',
            'spellbook_name',
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
        heads = obj.live_heads.all().order_by('created')
        return HydraHeadSerializer(heads, many=True).data

    def get_history(self, obj):
        heads = obj.finished_heads.all().order_by('created')
        return HydraHeadSerializer(heads, many=True).data

    def get_subgraphs(self, obj):
        # Fetch children spawns
        live = list(obj.live_head_spawns)
        finished = list(obj.finished_head_spawns)
        children = live + finished
        children.sort(key=lambda x: x.created if x.created else x.modified)

        # Recursive serialization for nested swimlanes
        return HydraSwimlaneSerializer(children, many=True).data
