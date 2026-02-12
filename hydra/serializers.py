import json
import re
from typing import Any, Dict, List, Optional

from rest_framework import serializers

from common.constants import ALL_FIELDS
from environments.variable_renderer import VariableRenderer
from hydra import constants

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
    HydraTag,
    HydraWireType,
)

# --- Top-Level Helpers ---


def _get_ui_data(json_str: str) -> Dict[str, int]:
    """Parses UI JSON with a safe fallback."""
    try:
        return json.loads(json_str)
    except (ValueError, TypeError):
        return {constants.KEY_X: 100, constants.KEY_Y: 100}


def _get_wire_status_label(type_id: int) -> str:
    """Maps wire IDs to frontend status strings."""
    mapping = {
        HydraWireType.TYPE_FLOW: constants.TYPE_FLOW_STR,
        HydraWireType.TYPE_SUCCESS: constants.TYPE_SUCCESS_STR,
        HydraWireType.TYPE_FAILURE: constants.TYPE_FAIL_STR,
    }
    return mapping.get(type_id, constants.TYPE_FLOW_STR)


def _extract_variables_from_spell(spell: Optional[HydraSpell]) -> set:
    """Scans a spell's arguments and switches for template variables."""
    variables = set()
    if not spell:
        return variables

    # Scan Arguments
    for a in spell.hydraspellargumentassignment_set.all():
        found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
        variables.update(found)

    # Scan Switches
    for s in spell.switches.all():
        raw = s.flag + (s.value or '')
        found = re.findall(r'\{\{\s*(\w+)\s*\}\}', raw)
        variables.update(found)

    # Scan Executable Arguments
    for a in spell.talos_executable.talosexecutableargumentassignment_set.all():
        found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
        variables.update(found)

    return variables


def _build_context_matrix(
    spell: Optional[HydraSpell],
    global_context: Dict[str, Any],
    node_overrides: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Constructs the 'Smart Matrix' of variable resolution."""
    variables = _extract_variables_from_spell(spell)
    matrix = []

    for var in sorted(list(variables)):
        item = {
            'key': var,
            'source': 'default',
            'value': '',
            'display_value': '',
            'is_readonly': False,
        }

        if var in node_overrides:
            item.update(
                {
                    'source': 'override',
                    'value': node_overrides[var],
                    'display_value': node_overrides[var],
                }
            )
        elif var in global_context:
            val_str = str(global_context[var])
            item.update(
                {
                    'source': 'global',
                    'value': global_context[var],
                    'display_value': val_str,
                    'is_readonly': True,
                }
            )

        matrix.append(item)
    return matrix


def _tail_log(text: Optional[str]) -> str:
    """Returns the last 20 lines of a log string."""
    if not text:
        return ''
    lines = text.splitlines()
    tail = lines[-20:] if len(lines) > 20 else lines
    return '\n'.join(tail)


# --- Serializers ---


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
        """Helper to show what the command WOULD look like with default env."""
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


class HydraSpellbookNodeSerializer(serializers.ModelSerializer):
    spell_name = serializers.CharField(source='spell.name', read_only=True)
    invoked_spellbook_name = serializers.CharField(
        source='invoked_spellbook.name', read_only=True
    )
    ui = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    has_override = serializers.SerializerMethodField()
    context_overrides = HydraSpellBookNodeContextSerializer(
        source='hydraspellbooknodecontext_set', many=True, read_only=True
    )

    class Meta:
        model = HydraSpellbookNode
        fields = ALL_FIELDS

    def get_ui(self, obj):
        return _get_ui_data(obj.ui_json)

    def get_title(self, obj):
        if obj.invoked_spellbook_id:
            return obj.invoked_spellbook.name
        return obj.spell.name if obj.spell else constants.VAL_UNKNOWN

    def get_has_override(self, obj):
        return obj.distribution_mode_id is not None


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
    """Flattened serializer specifically for the Graph Editor frontend."""

    nodes = serializers.SerializerMethodField()
    connections = serializers.SerializerMethodField()

    class Meta:
        model = HydraSpellbook
        fields = [constants.KEY_ID, 'nodes', 'connections']

    def get_nodes(self, obj):
        nodes_data = []
        for n in obj.nodes.all().select_related('spell', 'invoked_spellbook'):
            ui = _get_ui_data(n.ui_json)
            is_delegated = bool(n.invoked_spellbook_id)
            is_root = (n.spell_id == HydraSpell.BEGIN_PLAY) and not is_delegated
            title = (
                n.invoked_spellbook.name
                if is_delegated
                else (n.spell.name if n.spell else constants.VAL_UNKNOWN)
            )

            node_dict = {
                constants.KEY_ID: n.id,
                constants.KEY_TITLE: title,
                constants.KEY_X: ui.get(constants.KEY_X, 0),
                constants.KEY_Y: ui.get(constants.KEY_Y, 0),
                constants.KEY_SPELL_ID: n.spell_id,
                constants.KEY_IS_ROOT: is_root,
                'has_override': n.distribution_mode_id is not None,
            }
            if is_delegated:
                node_dict['invoked_spellbook_id'] = str(n.invoked_spellbook_id)
            nodes_data.append(node_dict)
        return nodes_data

    def get_connections(self, obj):
        wires_data = []
        for w in obj.wires.all():
            wires_data.append(
                {
                    'from_node_id': w.source_id,
                    'to_node_id': w.target_id,
                    'status_id': _get_wire_status_label(w.type_id),
                }
            )
        return wires_data


class HydraNodeDetailsSerializer(serializers.ModelSerializer):
    """Provides deep context analysis for the Inspector panel."""

    context_matrix = serializers.SerializerMethodField()

    class Meta:
        model = HydraSpellbookNode
        fields = [
            constants.KEY_ID,
            'spell',
            'distribution_mode',
            'context_matrix',
        ]

    def get_context_matrix(self, obj):
        global_context = VariableRenderer.extract_variables(
            obj.spellbook.environment
        )
        overrides = {
            c.key: c.value for c in obj.hydraspellbooknodecontext_set.all()
        }
        return _build_context_matrix(obj.spell, global_context, overrides)


class HydraHeadSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    target_name = serializers.CharField(
        source='target.hostname', read_only=True
    )

    class Meta:
        model = HydraHead
        fields = ALL_FIELDS


class HydraNodeTelemetrySerializer(serializers.ModelSerializer):
    """
    Rich telemetry for a running Head, including logs and reconstructed commands.
    """

    status_name = serializers.CharField(source='status.name', read_only=True)
    logs = serializers.SerializerMethodField()
    exec_logs = serializers.SerializerMethodField()
    command = serializers.SerializerMethodField()
    context_matrix = serializers.SerializerMethodField()
    agent = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()

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
            'context_matrix',
            'duration',
        ]

    def get_agent(self, obj):
        return str(obj.target) if obj.target else constants.VAL_PENDING

    def get_duration(self, obj):
        # Placeholder pending start/end timestamp implementation on Head
        return '0s'

    def get_logs(self, obj):
        return _tail_log(obj.spell_log)

    def get_exec_logs(self, obj):
        return _tail_log(obj.execution_log)

    def get_command(self, obj):
        if not (obj.spell and obj.node):
            return constants.VAL_CMD_NOT_CAPTURED

        try:
            overrides = {
                c.key: c.value
                for c in obj.node.hydraspellbooknodecontext_set.all()
            }
            env = (
                obj.spawn.spellbook.environment
                if (obj.spawn and obj.spawn.spellbook)
                else None
            )
            cmd_list = obj.spell.get_full_command(
                environment=env, extra_context=overrides
            )
            return ' '.join(cmd_list)
        except Exception as e:
            return f'Error interpreting command: {e}'

    def get_context_matrix(self, obj):
        env = (
            obj.spawn.spellbook.environment
            if (obj.spawn and obj.spawn.spellbook)
            else None
        )
        global_context = VariableRenderer.extract_variables(env)

        overrides = {}
        if obj.node:
            overrides = {
                c.key: c.value
                for c in obj.node.hydraspellbooknodecontext_set.all()
            }

        return _build_context_matrix(obj.spell, global_context, overrides)


class HydraSpawnSerializer(serializers.ModelSerializer):
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


class HydraSpawnStatusSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='status.name', read_only=True)
    nodes = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = HydraSpawn
        fields = ['status', 'status_label', 'is_active', 'nodes']

    def get_nodes(self, obj):
        node_status_map = {}

        # Inject BeginPlay status manually since it doesn't always have a Head
        if obj.spellbook:
            begin_play_node = obj.spellbook.nodes.filter(
                spell_id=HydraSpell.BEGIN_PLAY
            ).first()
            if begin_play_node:
                node_status_map[str(begin_play_node.id)] = {
                    'status_id': constants.HydraStatusID.SUCCESS,
                    'head_id': None,
                }

        # Map actual execution heads
        for head in obj.heads.all().order_by('created'):
            if head.node_id:
                child = head.child_spawns.first()
                child_id = str(child.id) if child else None

                node_status_map[str(head.node_id)] = {
                    'status_id': head.status_id,
                    'head_id': str(head.id),
                    'child_spawn_id': child_id,
                }
        return node_status_map
