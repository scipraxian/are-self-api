import json
import re

from rest_framework import serializers

from environments.models import ProjectEnvironment
from environments.variable_renderer import VariableRenderer
from .models import (
    HydraDistributionMode,
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellArgumentAssignment,
    HydraSpellBookNodeContext,
    HydraSpellbook,
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraSpellContext,
    HydraSpellTarget,
    HydraStatusID,
    HydraTag,
    HydraWireType,
)

# --- Basic Serializers ---


class HydraTagSerializer(serializers.ModelSerializer):

    class Meta:
        model = HydraTag
        fields = ['id', 'name']


class HydraDistributionModeSerializer(serializers.ModelSerializer):

    class Meta:
        model = HydraDistributionMode
        fields = ['id', 'name', 'description']


class HydraSpellContextSerializer(serializers.ModelSerializer):

    class Meta:
        model = HydraSpellContext
        fields = ['id', 'spell', 'key', 'value']


class HydraSpellTargetSerializer(serializers.ModelSerializer):
    target_name = serializers.CharField(source='target.hostname',
                                        read_only=True)

    class Meta:
        model = HydraSpellTarget
        fields = ['id', 'spell', 'target', 'target_name']


class HydraSpellArgumentAssignmentSerializer(serializers.ModelSerializer):
    argument_name = serializers.CharField(source='argument.argument',
                                          read_only=True)

    class Meta:
        model = HydraSpellArgumentAssignment
        fields = ['id', 'spell', 'order', 'argument', 'argument_name']


class HydraSpellSerializer(serializers.ModelSerializer):
    tags = HydraTagSerializer(many=True, read_only=True)
    executable_name = serializers.CharField(source='talos_executable.name',
                                            read_only=True)
    rendered_command = serializers.SerializerMethodField()
    args = HydraSpellArgumentAssignmentSerializer(
        source='hydraspellargumentassignment_set', many=True, read_only=True)
    targets = HydraSpellTargetSerializer(source='specific_targets',
                                         many=True,
                                         read_only=True)

    class Meta:
        model = HydraSpell
        fields = [
            'id', 'name', 'description', 'created', 'modified', 'is_favorite',
            'tags', 'switches', 'distribution_mode', 'executable_name',
            'rendered_command', 'args', 'targets', 'talos_executable'
        ]

    def get_rendered_command(self, obj) -> str:
        """Helper to show what the command WOULD look like with default env."""
        env = self.context.get('environment')
        cmd_list = obj.get_full_command(environment=env)
        return ' '.join(cmd_list)


class HydraSpellBookNodeContextSerializer(serializers.ModelSerializer):

    class Meta:
        model = HydraSpellBookNodeContext
        fields = ['id', 'node', 'key', 'value']


class HydraSpellbookConnectionWireSerializer(serializers.ModelSerializer):
    type_name = serializers.CharField(source='type.name', read_only=True)
    status_id = serializers.SerializerMethodField()

    class Meta:
        model = HydraSpellbookConnectionWire
        fields = [
            'id', 'spellbook', 'source', 'target', 'type', 'type_name',
            'status_id', 'created', 'modified'
        ]

    def get_status_id(self, obj):
        type_to_string = {
            HydraWireType.TYPE_FLOW: 'flow',
            HydraWireType.TYPE_SUCCESS: 'success',
            HydraWireType.TYPE_FAILURE: 'fail',
        }
        return type_to_string.get(obj.type_id, 'flow')


class HydraSpellbookNodeSerializer(serializers.ModelSerializer):
    spell_name = serializers.CharField(source='spell.name', read_only=True)
    invoked_spellbook_name = serializers.CharField(
        source='invoked_spellbook.name', read_only=True)
    ui = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    has_override = serializers.SerializerMethodField()
    context_overrides = HydraSpellBookNodeContextSerializer(
        source='hydraspellbooknodecontext_set', many=True, read_only=True)

    class Meta:
        model = HydraSpellbookNode
        fields = [
            'id', 'spellbook', 'spell', 'spell_name', 'is_root', 'ui_json',
            'ui', 'invoked_spellbook', 'invoked_spellbook_name',
            'distribution_mode', 'title', 'has_override', 'context_overrides'
        ]

    def get_ui(self, obj):
        try:
            return json.loads(obj.ui_json)
        except (ValueError, TypeError):
            return {'x': 100, 'y': 100}

    def get_title(self, obj):
        if obj.invoked_spellbook_id:
            return obj.invoked_spellbook.name
        return obj.spell.name if obj.spell else 'Unknown'

    def get_has_override(self, obj):
        return obj.distribution_mode_id is not None


class HydraSpellbookSerializer(serializers.ModelSerializer):
    environment_name = serializers.CharField(source='environment.name',
                                             read_only=True)
    node_count = serializers.IntegerField(source='nodes.count', read_only=True)
    tags = HydraTagSerializer(many=True, read_only=True)

    class Meta:
        model = HydraSpellbook
        fields = [
            'id', 'name', 'description', 'created', 'modified', 'is_favorite',
            'tags', 'ui_json', 'environment', 'environment_name', 'node_count'
        ]


# --- Graph Layout (Custom Logic Replacement) ---


class HydraGraphLayoutSerializer(serializers.ModelSerializer):
    """
    Serializer specifically designed to replace 'get_graph_layout' view logic.
    """
    nodes = serializers.SerializerMethodField()
    connections = serializers.SerializerMethodField()

    class Meta:
        model = HydraSpellbook
        fields = ['id', 'nodes', 'connections']

    def get_nodes(self, obj):
        # Using nested serializer logic but flattened for the specific frontend requirement keys
        result = []
        # Ensure root exists (logic from view)
        if not obj.nodes.filter(is_root=True).exists():
            # Side-effect inside serializer? Just for read, we won't mutate.
            # But the view logic DID create it.
            # To be safe, we assume it exists or the view ensures it before serialization.
            pass

        nodes = obj.nodes.all().select_related('spell', 'invoked_spellbook')
        for n in nodes:
            try:
                ui = json.loads(n.ui_json)
            except json.JSONDecodeError:
                ui = {'x': 100, 'y': 100}

            is_delegated = bool(n.invoked_spellbook_id)
            is_root = (n.spell_id == HydraSpell.BEGIN_PLAY) and not is_delegated
            title = n.invoked_spellbook.name if is_delegated else n.spell.name

            data = {
                'id': n.id,
                'title': title,
                'x': ui.get('x', 0),
                'y': ui.get('y', 0),
                'spell_id': n.spell_id,
                'is_root': is_root,
                'has_override': n.distribution_mode_id is not None,
            }
            if is_delegated:
                data['invoked_spellbook_id'] = str(n.invoked_spellbook_id)
            result.append(data)
        return result

    def get_connections(self, obj):
        result = []
        type_to_string = {
            HydraWireType.TYPE_FLOW: 'flow',
            HydraWireType.TYPE_SUCCESS: 'success',
            HydraWireType.TYPE_FAILURE: 'fail',
        }
        for w in obj.wires.all():
            result.append({
                'from_node_id': w.source_id,
                'to_node_id': w.target_id,
                'status_id': type_to_string.get(w.type_id, 'flow')
            })
        return result


# --- Node Telemetry / Details Logic ---


class HydraNodeDetailsSerializer(serializers.ModelSerializer):
    """
    Replaces get_node_details logic.
    """
    context_matrix = serializers.SerializerMethodField()

    class Meta:
        model = HydraSpellbookNode
        fields = ['id', 'spell', 'distribution_mode', 'context_matrix']

    def get_context_matrix(self, obj):
        # 1. Identify Variables
        variables = set()
        if obj.spell:
            for a in obj.spell.hydraspellargumentassignment_set.all():
                found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
                variables.update(found)
            for s in obj.spell.switches.all():
                found = re.findall(r'\{\{\s*(\w+)\s*\}\}',
                                   s.flag + (s.value or ''))
                variables.update(found)
            for a in obj.spell.talos_executable.talosexecutableargumentassignment_set.all(
            ):
                found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
                variables.update(found)

        # 2. Global Context
        global_context = VariableRenderer.extract_variables(
            obj.spellbook.environment)

        # 3. Overrides
        overrides = {
            c.key: c.value for c in obj.hydraspellbooknodecontext_set.all()
        }

        matrix = []
        for var in sorted(list(variables)):
            item = {
                'key': var,
                'source': 'default',
                'value': '',
                'display_value': '',
                'is_readonly': False,
            }
            if var in overrides:
                item['source'] = 'override'
                item['value'] = overrides[var]
                item['display_value'] = overrides[var]
            elif var in global_context:
                item['source'] = 'global'
                item['value'] = global_context[var]
                item['display_value'] = str(global_context[var])
                item['is_readonly'] = True

            matrix.append(item)
        return matrix


class HydraHeadSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    target_name = serializers.CharField(source='target.hostname',
                                        read_only=True)

    class Meta:
        model = HydraHead
        fields = [
            'id', 'status', 'status_name', 'spawn', 'node', 'spell',
            'provenance', 'target', 'target_name', 'created', 'modified',
            'result_code'
        ]


class HydraNodeTelemetrySerializer(serializers.ModelSerializer):
    """
    Replaces get_node_telemetry logic. Serializes a HydraHead but adds computed context fields.
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
            'id', 'status', 'status_name', 'result_code', 'agent', 'logs',
            'exec_logs', 'command', 'context_matrix', 'duration'
        ]

    def get_agent(self, obj):
        return str(obj.target) if obj.target else 'Pending...'

    def get_duration(self, obj):
        return '0s'  # Placeholder as per original

    def get_logs(self, obj):
        logs = obj.spell_log or ''
        log_lines = logs.split('\n')
        tail = log_lines[-20:] if len(log_lines) > 20 else log_lines
        return '\n'.join(tail)

    def get_exec_logs(self, obj):
        logs = obj.execution_log or ''
        lines = logs.split('\n')
        tail = lines[-20:] if len(lines) > 20 else lines
        return '\n'.join(tail)

    def get_command(self, obj):
        # 1. Try to find in logs
        if obj.execution_log and 'Command:' in obj.execution_log:
            pass  # Return extracted? Original code does pass then proceeds to reconstruction logic if spell exists

        # 2. Reconstruct if possible
        command = 'Command not captured.'
        if obj.spell and obj.node:
            try:
                overrides = {
                    c.key: c.value
                    for c in obj.node.hydraspellbooknodecontext_set.all()
                }
                # Need environment from spawn->spellbook
                env = None
                if obj.spawn and obj.spawn.spellbook:
                    env = obj.spawn.spellbook.environment

                cmd_list = obj.spell.get_full_command(environment=env,
                                                      extra_context=overrides)
                command = ' '.join(cmd_list)
            except Exception as e:
                command = f'Error interpreting command: {e}'
        return command

    def get_context_matrix(self, obj):
        variables = set()
        if obj.spell:
            # Args
            for a in obj.spell.hydraspellargumentassignment_set.all():
                found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
                variables.update(found)
            # Switches
            for s in obj.spell.switches.all():
                found = re.findall(r'\{\{\s*(\w+)\s*\}\}',
                                   s.flag + (s.value or ''))
                variables.update(found)
            # Exec Args
            for a in obj.spell.talos_executable.talosexecutableargumentassignment_set.all(
            ):
                found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
                variables.update(found)

        global_context = {}
        if obj.spawn and obj.spawn.spellbook and obj.spawn.spellbook.environment:
            global_context = VariableRenderer.extract_variables(
                obj.spawn.spellbook.environment)

        overrides = {}
        if obj.node:
            overrides = {
                c.key: c.value
                for c in obj.node.hydraspellbooknodecontext_set.all()
            }

        matrix = []
        for var in sorted(list(variables)):
            val = ''
            source = 'default'

            if var in overrides:
                val = overrides[var]
                source = 'override'
            elif var in global_context:
                val = str(global_context[var])
                source = 'global'

            matrix.append({'key': var, 'value': val, 'source': source})
        return matrix


# --- Spawn Logic ---


class HydraSpawnSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source='status.name', read_only=True)
    spellbook_name = serializers.CharField(source='spellbook.name',
                                           read_only=True)
    environment_name = serializers.CharField(source='environment.name',
                                             read_only=True)

    class Meta:
        model = HydraSpawn
        fields = [
            'id', 'spellbook', 'spellbook_name', 'status', 'status_name',
            'created', 'modified', 'environment', 'environment_name',
            'context_data', 'parent_head', 'is_active', 'is_alive', 'is_dead',
            'is_queued'
        ]


class HydraSpawnStatusSerializer(serializers.ModelSerializer):
    """
    Replaces get_execution_status.
    """
    status_label = serializers.CharField(source='status.name', read_only=True)
    nodes = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = HydraSpawn
        fields = ['status', 'status_label', 'is_active', 'nodes']

    def get_nodes(self, obj):
        node_status_map = {}

        # Add Begin Play (Always Success if Spawn exists) - View logic
        if obj.spellbook:
            begin_play_node = obj.spellbook.nodes.filter(
                spell_id=HydraSpell.BEGIN_PLAY).first()
            if begin_play_node:
                node_status_map[str(begin_play_node.id)] = {
                    'status_id': HydraStatusID.SUCCESS,
                    'head_id': None,
                }

        for head in obj.heads.all().order_by('created'):
            if head.node_id:
                head_data = {
                    'status_id': head.status_id,
                    'head_id': str(head.id),
                }
                child = head.child_spawns.first()
                if child:
                    head_data['child_spawn_id'] = str(child.id)
                node_status_map[str(head.node_id)] = head_data
        return node_status_map
