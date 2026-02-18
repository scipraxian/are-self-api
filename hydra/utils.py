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
    HEAD_FIELD_NAME,
    KEY_BOOK_ID,
    KEY_ENVIRONMENT_ID,
    KEY_HEAD_ID,
    KEY_PROVENANCE_ID,
    KEY_SPAWN_ID,
    KEY_SPELL_ID,
    NODE_FIELD_NAME,
    PROVENANCE_FIELD_NAME,
    RESULT_CODE_FIELD_NAME,
    SPAWN_FIELD_NAME,
    SPELL_LOG_FIELD_NAME,
    SPELLBOOK_FIELD_NAME,
)
from hydra.models import HydraHead, HydraSpellBookNodeContext, HydraSpellContext

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

    Hierarchy of Variable Precedence (Lowest to Highest):
    1. Global Environment (ProjectEnvironment context)
    2. Spell Defaults (HydraSpellContext)
    3. Node Overrides (HydraSpellBookNodeContext)
    4. Runtime Injection (HydraSpawn.context_data)
    """
    metadata: Dict[str, Any] = {}
    head = None

    # 1. Resolve Head and Base IDs
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
                'node',
                'node__environment',
                'spawn',
                'spawn__environment',
                'spawn__spellbook',
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
    else:
        raise ValueError('Must provide either head_id or (env_id and spell_id)')

    context_data = metadata.copy()
    if head:
        context_data[HEAD_FIELD_NAME] = head
        context_data[SPAWN_FIELD_NAME] = head.spawn
        if head.node:
            context_data[NODE_FIELD_NAME] = head.node
        if head.spawn.spellbook:
            context_data[SPELLBOOK_FIELD_NAME] = head.spawn.spellbook
    if env:
        context_data.update(VariableRenderer.extract_variables(env))

    if not head:
        if spell_id:
            spell_vars = HydraSpellContext.objects.filter(spell_id=spell_id)
            for var in spell_vars:
                if var.key:
                    context_data[var.key] = var.value
        return context_data

    if head.blackboard and isinstance(head.blackboard, dict):
        context_data.update(head.blackboard)

    if head.spell:
        spell_vars = HydraSpellContext.objects.filter(spell=head.spell)
        for var in spell_vars:
            if var.key:
                context_data[var.key] = var.value
    if head.node:
        node_vars = HydraSpellBookNodeContext.objects.filter(node=head.node)
        for var in node_vars:
            if var.key:
                context_data[var.key] = var.value

    return context_data
