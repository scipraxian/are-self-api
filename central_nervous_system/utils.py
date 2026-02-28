import datetime
import json
import logging
import uuid
from typing import Any, Dict, NamedTuple

from common.constants import ID
from environments.models import ProjectEnvironment
from environments.variable_renderer import VariableRenderer
from central_nervous_system.constants import (
    EXECUTION_LOG_FIELD_NAME,
    HEAD_FIELD_NAME,
    KEY_BOOK_ID,
    KEY_ENVIRONMENT_ID,
    KEY_HEAD_ID,
    KEY_PROVENANCE_ID,
    KEY_SPAWN_ID,
    KEY_SPELL_ID,
    NEURON_FIELD_NAME,
    PROVENANCE_FIELD_NAME,
    RESULT_CODE_FIELD_NAME,
    SPAWN_FIELD_NAME,
    APPLICATION_LOG_FIELD_NAME,
    SPELLBOOK_FIELD_NAME,
)
from central_nervous_system.models import Spike, NeuronContext, EffectorContext

logger = logging.getLogger(__name__)


# TODO: everything here should be moved to somewhere more descriptive.


class CNSContext(NamedTuple):  # depreciated.
    project_root: str
    engine_root: str
    build_root: str
    staging_dir: str
    project_name: str
    dynamic_context: dict


def get_timestamp():
    return datetime.datetime.now().strftime('%H:%M:%S')


def log_system(spike, message):
    entry = f'[{get_timestamp()}] {message}\n'
    spike.execution_log += entry
    spike.save(update_fields=['execution_log'])


def get_active_environment(spike) -> Any:
    """Determines the active ProjectEnvironment for a given Head."""
    if not spike:
        return None

    if spike.neuron and spike.neuron.environment:
        return spike.neuron.environment
    elif spike.spike_train.environment:
        return spike.spike_train.environment
    elif spike.spike_train.pathway and spike.spike_train.pathway.environment:
        return spike.spike_train.pathway.environment

    return None


def resolve_environment_context(
    head_id: uuid.UUID = None,
    spell_id: uuid.UUID = None,
) -> Dict[str, Any]:
    """Resolves the active ProjectEnvironment and builds the context dictionary.

    Hierarchy of Variable Precedence (Lowest to Highest):
    1. Global Environment (ProjectEnvironment context)
    2. Effector Defaults (EffectorContext)
    3. Node Overrides (NeuronContext)
    4. Runtime Injection (SpikeTrain.context_data)
    """
    metadata: Dict[str, Any] = {}
    spike = None

    # 1. Resolve Spike and Base IDs
    if spell_id and not head_id:
        env = ProjectEnvironment.objects.get(
            id=ProjectEnvironment.DEFAULT_ENVIRONMENT
        )
        metadata = {
            KEY_SPELL_ID: spell_id if spell_id else None,
            KEY_ENVIRONMENT_ID: str(env.id) if env else None,
        }
    elif head_id:
        try:
            spike = Spike.objects.select_related(
                'effector',
                'neuron',
                'neuron__environment',
                'spike_train',
                'spike_train__environment',
                'spike_train__pathway',
                'spike_train__pathway__environment',
                PROVENANCE_FIELD_NAME,
            ).get(id=head_id)
        except Spike.DoesNotExist:
            return {}

        env = get_active_environment(spike)

        metadata = {
            KEY_HEAD_ID: str(spike.id),
            KEY_SPAWN_ID: str(spike.spike_train.id),
            KEY_SPELL_ID: spike.effector.id if spike.effector else None,
            KEY_BOOK_ID: str(spike.spike_train.pathway.id)
            if spike.spike_train.pathway
            else None,
            KEY_PROVENANCE_ID: str(spike.provenance.id)
            if spike.provenance
            else None,
            KEY_ENVIRONMENT_ID: str(env.id) if env else None,
        }
        if spike.provenance:
            metadata[PROVENANCE_FIELD_NAME] = {
                ID: str(spike.provenance.id),
                APPLICATION_LOG_FIELD_NAME: spike.provenance.application_log or '',
                EXECUTION_LOG_FIELD_NAME: spike.provenance.execution_log or '',
                RESULT_CODE_FIELD_NAME: spike.provenance.result_code,
            }
        else:
            metadata[PROVENANCE_FIELD_NAME] = {
                ID: '',
                APPLICATION_LOG_FIELD_NAME: '',
                EXECUTION_LOG_FIELD_NAME: '',
                RESULT_CODE_FIELD_NAME: '',
            }
    else:
        raise ValueError('Must provide either head_id or (env_id and spell_id)')

    context_data = metadata.copy()
    if spike:
        context_data[HEAD_FIELD_NAME] = spike
        context_data[SPAWN_FIELD_NAME] = spike.spike_train
        if spike.neuron:
            context_data[NEURON_FIELD_NAME] = spike.neuron
        if spike.spike_train.pathway:
            context_data[SPELLBOOK_FIELD_NAME] = spike.spike_train.pathway
    if env:
        context_data.update(VariableRenderer.extract_variables(env))

    if not spike:
        if spell_id:
            spell_vars = EffectorContext.objects.filter(spell_id=spell_id)
            for var in spell_vars:
                if var.key:
                    context_data[var.key] = var.value
        return context_data

    if spike.blackboard and isinstance(spike.blackboard, dict):
        context_data.update(spike.blackboard)

    if spike.effector:
        spell_vars = EffectorContext.objects.filter(effector=spike.effector)
        for var in spell_vars:
            if var.key:
                context_data[var.key] = var.value
    if spike.neuron:
        node_vars = NeuronContext.objects.filter(neuron=spike.neuron)
        for var in node_vars:
            if var.key:
                context_data[var.key] = var.value

    return context_data
