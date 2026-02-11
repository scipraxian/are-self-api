import datetime
import uuid
from typing import Any, Dict, NamedTuple

from environments.variable_renderer import VariableRenderer

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


def resolve_template(template_str, context: HydraContext):
    if not template_str:
        return ''
    format_data = context._asdict()
    if context.dynamic_context:
        format_data.update(context.dynamic_context)
    try:
        return template_str.format(**format_data)
    except KeyError:
        return template_str


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
    from environments.models import ProjectEnvironment
    from hydra.constants import (
        KEY_BOOK_ID,
        KEY_ENVIRONMENT_ID,
        KEY_HEAD_ID,
        KEY_PROVENANCE_ID,
        KEY_SPAWN_ID,
        KEY_SPELL_ID,
    )
    from hydra.models import HydraHead

    env = None
    metadata = {}

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
    else:
        raise ValueError('Must provide either head_id or (env_id and spell_id)')

    if not env:
        return metadata

    context_data = metadata.copy()
    context_data.update(VariableRenderer.extract_variables(env))

    return context_data
