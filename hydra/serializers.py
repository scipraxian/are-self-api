import json
from typing import Optional

from django.utils import timezone
from rest_framework import serializers

from common.constants import ALL_FIELDS
from hydra import constants
from hydra.utils import get_active_environment, resolve_environment_context

from .models import (
    HydraDistributionMode,
    HydraHead,
    HydraHeadStatus,
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


def _get_wire_status_label(type_id: int) -> str:
    """Maps wire IDs to frontend status strings."""
    mapping = {
        HydraWireType.TYPE_FLOW: constants.TYPE_FLOW_STR,
        HydraWireType.TYPE_SUCCESS: constants.TYPE_SUCCESS_STR,
        HydraWireType.TYPE_FAILURE: constants.TYPE_FAIL_STR,
    }
    return mapping.get(type_id, constants.TYPE_FLOW_STR)


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
    """
    Writable serializer for node-specific variable overrides.
    """

    class Meta:
        model = HydraSpellBookNodeContext
        fields = ALL_FIELDS


class HydraSpellbookConnectionWireSerializer(serializers.ModelSerializer):
    """
    Graph Wires. Writable.
    """

    type_name = serializers.CharField(source='type.name', read_only=True)
    status_id = serializers.SerializerMethodField()  # Frontend compat

    class Meta:
        model = HydraSpellbookConnectionWire
        fields = ALL_FIELDS

    def get_status_id(self, obj):
        return _get_wire_status_label(obj.type_id)

    def validate(self, data):
        """Graph Integrity: Ensure Source and Target belong to the SAME Book."""
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
    """
    Graph Nodes. Writable.
    """

    spell_name = serializers.CharField(source='spell.name', read_only=True)
    invoked_spellbook_name = serializers.CharField(
        source='invoked_spellbook.name', read_only=True
    )

    # [FIX] Writable JSON Field for UI coordinates
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
        """Ensure UI data is serialized to string for the TextField model."""
        if isinstance(value, dict):
            return json.dumps(value)
        return value

    def to_representation(self, instance):
        """Convert the TextField JSON back to a Dict for the frontend."""
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


class HydraSpawnCreateSerializer(serializers.Serializer):
    """
    Action Serializer. Validates Launch Request.
    """

    spellbook_id = serializers.UUIDField()
    environment_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_spellbook_id(self, value):
        if not HydraSpellbook.objects.filter(id=value).exists():
            raise serializers.ValidationError('Spellbook not found.')
        return value


class HydraHeadSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for lists (NO LOGS).
    """

    status_name = serializers.CharField(source='status.name', read_only=True)
    target_name = serializers.CharField(
        source='target.hostname', read_only=True
    )

    class Meta:
        model = HydraHead
        # EXPLICITLY excluding spell_log and execution_log to prevent bloat
        exclude = ['spell_log', 'execution_log']


class HydraNodeTelemetrySerializer(serializers.ModelSerializer):
    """
    Rich, heavy telemetry for Inspector panels.
    Includes logs, durations, and fully resolved commands.
    """

    status_name = serializers.CharField(source='status.name', read_only=True)
    logs = serializers.SerializerMethodField()
    exec_logs = serializers.SerializerMethodField()
    command = serializers.SerializerMethodField()
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
            'duration',
        ]

    def get_agent(self, obj):
        return str(obj.target) if obj.target else constants.VAL_PENDING

    def get_duration(self, obj) -> str:
        """Calculates runtime duration."""
        if not obj.created:
            return '0s'

        # If finished (Success/Failed/Aborted), use modified - created
        # Note: This assumes 'modified' is updated upon completion, which Hydra logic does.
        is_terminal = obj.status_id in HydraHeadStatus.IS_TERMINAL_STATUS_LIST
        end_time = obj.modified if is_terminal else timezone.now()

        delta = end_time - obj.created
        total_seconds = int(delta.total_seconds())

        minutes = total_seconds // 60
        seconds = total_seconds % 60

        if minutes > 0:
            return f'{minutes}m {seconds}s'
        return f'{seconds}s'

    def get_logs(self, obj):
        return _tail_log(obj.spell_log)

    def get_exec_logs(self, obj):
        return _tail_log(obj.execution_log)

    def get_command(self, obj) -> str:
        """
        Reconstructs the actual command string used/to-be-used.
        """
        try:
            if not obj.spell:
                return constants.VAL_CMD_NOT_CAPTURED

            # 1. Resolve Environment
            env = get_active_environment(obj)

            # 2. Resolve Full Context (Env vars + Spell Defaults + Node Overrides + Spawn Data)
            # This logic mimics GenericSpellCaster exactly.
            full_context = resolve_environment_context(head_id=obj.id)

            # 3. Generate Command List
            cmd_list = obj.spell.get_full_command(
                environment=env, extra_context=full_context
            )
            return ' '.join(cmd_list)

        except Exception as e:
            return f'Error resolving command: {str(e)}'


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
