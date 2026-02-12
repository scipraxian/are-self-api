import datetime
import json
import logging
import uuid
from typing import Any, Dict, NamedTuple

from common.constants import ID
from environments.models import ProjectEnvironment
from environments.variable_renderer import VariableRenderer
from hydra.constants import (
    EXECUTION_LOG_FIELD_NAME,
    KEY_BOOK_ID,
    KEY_ENVIRONMENT_ID,
    KEY_HEAD_ID,
    KEY_PROVENANCE_ID,
    KEY_SPAWN_ID,
    KEY_SPELL_ID,
    PROVENANCE_FIELD_NAME,
    RESULT_CODE_FIELD_NAME,
    SPELL_LOG_FIELD_NAME,
)
from hydra.models import HydraHead

logger = logging.getLogger(__name__)


# TODO: everything here should be moved to somewhere more descriptive.


class HydraContext(NamedTuple):  # depreciated.
    project_root: str
    engine_root: str
    build_root: str
    staging_dir: str
    project_name: str
    dynamic_context: dict


def get_timestamp():
    return datetime.datetime.now().strftime('%H:%M:%S')


def log_system(head, message):
    entry = f'[{get_timestamp()}] {message}\n'
    head.execution_log += entry
    head.save(update_fields=['execution_log'])


def get_active_environment(head) -> Any:
    """Determines the active ProjectEnvironment for a given Head."""
    if not head:
        return None

    if head.node and head.node.environment:
        return head.node.environment
    elif head.spawn.environment:
        return head.spawn.environment
    elif head.spawn.spellbook and head.spawn.spellbook.environment:
        return head.spawn.spellbook.environment

    return None


def resolve_environment_context(
    head_id: uuid.UUID = None,
    spell_id: uuid.UUID = None,
) -> Dict[str, Any]:
    """Resolves the active ProjectEnvironment and builds the context dictionary.

    Args:
        head_id: The UUID of the execution head.
        spell_id: The UUID of the spell (legacy fallback).

    Returns:
        A dictionary containing flattened environment variables and standard
        execution metadata (head_id, spawn_id, etc.).
    """
    # Local imports to avoid circular dependency with models.py if it ever imports utils

    env = None
    metadata: Dict[str, Any] = {}

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
            head = HydraHead.objects.select_related(
                'spell',
                'node__environment',
                'spawn__environment',
                'spawn__spellbook__environment',
                PROVENANCE_FIELD_NAME,
            ).get(id=head_id)
        except HydraHead.DoesNotExist:
            return {}

        env = get_active_environment(head)

        metadata = {
            KEY_HEAD_ID: str(head.id),
            KEY_SPAWN_ID: str(head.spawn.id),
            KEY_SPELL_ID: head.spell.id if head.spell else None,
            KEY_BOOK_ID: str(head.spawn.spellbook.id)
            if head.spawn.spellbook
            else None,
            KEY_PROVENANCE_ID: str(head.provenance.id)
            if head.provenance
            else None,
            KEY_ENVIRONMENT_ID: str(env.id) if env else None,
        }
        if head.provenance:
            metadata[PROVENANCE_FIELD_NAME] = {
                ID: str(head.provenance.id),
                SPELL_LOG_FIELD_NAME: head.provenance.spell_log or '',
                EXECUTION_LOG_FIELD_NAME: head.provenance.execution_log or '',
                RESULT_CODE_FIELD_NAME: head.provenance.result_code,
            }
        else:
            metadata[PROVENANCE_FIELD_NAME] = {
                ID: '',
                SPELL_LOG_FIELD_NAME: '',
                EXECUTION_LOG_FIELD_NAME: '',
                RESULT_CODE_FIELD_NAME: '',
            }

        # [NEW] 2. Merge Spawn Context Data (User Input / Dynamic vars)
        if head.spawn.context_data:
            try:
                dynamic_ctx = json.loads(head.spawn.context_data)
                if isinstance(dynamic_ctx, dict):
                    metadata.update(dynamic_ctx)
            except json.JSONDecodeError:
                logger.warning('Invalid JSON in Spawn Context Data.')

    else:
        raise ValueError('Must provide either head_id or (env_id and spell_id)')

    if not env:
        return metadata

    context_data = metadata.copy()
    context_data.update(VariableRenderer.extract_variables(env))

    return context_data
