import datetime
import json
import logging
import uuid
from typing import Any, Dict, NamedTuple

from common.constants import ID
from environments.models import ProjectEnvironment
from environments.variable_renderer import VariableRenderer
from central_nervous_system.constants import (
    APPLICATION_LOG_FIELD_NAME,
    EXECUTION_LOG_FIELD_NAME,
    HEAD_FIELD_NAME,
    KEY_ENVIRONMENT_ID,
    KEY_EFFECTOR_ID,
    KEY_PATHWAY_ID,
    KEY_PROVENANCE_ID,
    KEY_SPIKE_ID,
    KEY_SPIKE_TRAIN_ID,
    NEURON_FIELD_NAME,
    PROVENANCE_FIELD_NAME,
    RESULT_CODE_FIELD_NAME,
    SPELLBOOK_FIELD_NAME,
    SPAWN_FIELD_NAME,
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
    spike_id: uuid.UUID = None,
    effector_id: uuid.UUID = None,
) -> Dict[str, Any]:
    """Resolves the active ProjectEnvironment and builds the context dictionary.

    Hierarchy of Variable Precedence (Lowest to Highest):
    1. Global Environment (ProjectEnvironment context)
    2. SpikeTrain.cerebrospinal_fluid (train-level defaults)
    3. Spike.axoplasm (runtime state)
    4. Effector Defaults (EffectorContext)
    5. Node Overrides (NeuronContext)
    """
    metadata: Dict[str, Any] = {}
    spike = None

    # 1. Resolve Spike and Base IDs
    if effector_id and not spike_id:
        env = ProjectEnvironment.objects.get(
            id=ProjectEnvironment.DEFAULT_ENVIRONMENT
        )
        metadata = {
            KEY_EFFECTOR_ID: effector_id if effector_id else None,
            KEY_ENVIRONMENT_ID: str(env.id) if env else None,
        }
    elif spike_id:
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
            ).get(id=spike_id)
        except Spike.DoesNotExist:
            return {}

        env = get_active_environment(spike)

        metadata = {
            KEY_SPIKE_ID: str(spike.id),
            KEY_SPIKE_TRAIN_ID: str(spike.spike_train.id),
            KEY_EFFECTOR_ID: spike.effector.id if spike.effector else None,
            KEY_PATHWAY_ID: str(spike.spike_train.pathway.id)
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
        raise ValueError('Must provide either spike_id or (env_id and effector_id)')

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
        if effector_id:
            effector_vars = EffectorContext.objects.filter(effector_id=effector_id)
            for var in effector_vars:
                if var.key:
                    context_data[var.key] = var.value
        return context_data

    # Add SpikeTrain.cerebrospinal_fluid layer (train-level defaults)
    if (
        spike
        and spike.spike_train
        and spike.spike_train.cerebrospinal_fluid
        and isinstance(spike.spike_train.cerebrospinal_fluid, dict)
    ):
        context_data.update(spike.spike_train.cerebrospinal_fluid)

    # Add Spike.axoplasm layer (runtime state, overrides CSF)
    if spike.axoplasm and isinstance(spike.axoplasm, dict):
        context_data.update(spike.axoplasm)

    if spike.effector:
        effector_vars = EffectorContext.objects.filter(effector=spike.effector)
        for var in effector_vars:
            if var.key:
                context_data[var.key] = var.value
    if spike.neuron:
        node_vars = NeuronContext.objects.filter(neuron=spike.neuron)
        for var in node_vars:
            if var.key:
                context_data[var.key] = var.value

    return context_data
