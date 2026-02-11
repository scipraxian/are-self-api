import socket
import uuid
from typing import Any, Dict, List, Optional

from django.template import Context, Template

from environments.models import ContextVariable, ProjectEnvironment
from hydra.constants import (
    KEY_BOOK_ID,
    KEY_ENVIRONMENT_ID,
    KEY_HEAD_ID,
    KEY_PROVENANCE_ID,
    KEY_SERVER,
    KEY_SPAWN_ID,
    KEY_SPELL_ID,
)
from hydra.models import HydraHead, HydraSpell

DEFAULT_CONTEXT = {KEY_SERVER: socket.gethostname()}


def _resolve_environment_context(
    head_id: uuid.UUID = None,
    spell_id: uuid.UUID = None,
) -> Dict[str, Any]:
    """Resolves the active ProjectEnvironment and builds the context dictionary.

    Determines the environment based on the following priority hierarchy:
    1. Graph Node Override (HydraSpellbookNode.environment)
    2. Runtime Selection (HydraSpawn.environment)
    3. Default Fallback (HydraSpellbook.environment)

    Args:
        head_id: The UUID of the execution head.

    Returns:
        A dictionary containing flattened environment variables and standard
        execution metadata (head_id, spawn_id, etc.).
    """
    env = None
    if spell_id:
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
        if head.node and head.node.environment:
            env = head.node.environment
        elif head.spawn.environment:
            env = head.spawn.environment
        elif head.spawn.spellbook and head.spawn.spellbook.environment:
            env = head.spawn.spellbook.environment

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

    env_vars = ContextVariable.objects.filter(environment=env).select_related(
        'key'
    )
    for variable in env_vars:
        if variable.key and variable.key.name:
            context_data[variable.key.name] = variable.value

    return context_data


def _render_text(text: str, render_ctx: Context) -> str:
    """Renders a string template using the provided Django context."""
    if not text:
        return ''
    if '{{' not in text:
        return text
    return Template(text).render(render_ctx)


def spell_switches_and_arguments(
    spell_id: Optional[uuid.UUID] = None,
    head_id: Optional[uuid.UUID] = None,
    extra_context: Optional[dict] = None,
) -> List[str]:
    """Resolves and renders the arguments and switches for a Spell.

    Supports both legacy integer-based lookup and modern Head-based resolution.
    If a head_id is provided, it triggers the environment hierarchy resolution
    and injects project-specific variables.

    Args:
        spell_id: Legacy Spell ID. Ignored if head_id resolves a spell.
        head_id: UUID of the HydraHead. Triggers context resolution.
        extra_context: Dictionary of runtime overrides.

    Returns:
        A list of rendered command-line arguments and switches.

    Raises:
        ValueError: If no valid spell ID can be resolved.
    """
    full_context = DEFAULT_CONTEXT.copy()
    if head_id:
        spell_id = HydraHead.objects.get(id=head_id).spell.id
        env_context = _resolve_environment_context(head_id=head_id)
        full_context.update(env_context)
    elif spell_id:
        env_context = _resolve_environment_context(spell_id=spell_id)
        full_context.update(env_context)
    else:
        raise ValueError('Must provide either spell_id or head_id')

    if extra_context:
        full_context.update(extra_context)

    render_ctx = Context(full_context)

    spell = (
        HydraSpell.objects.select_related('talos_executable')
        .prefetch_related(
            'talos_executable__talosexecutableargumentassignment_set__argument',
            'hydraspellargumentassignment_set__argument',
            'talos_executable__switches',
            'switches',
        )
        .get(id=spell_id)
    )

    ordered_arguments_list = []

    executable_args = (
        spell.talos_executable.talosexecutableargumentassignment_set.all()
    )
    spell_args = spell.hydraspellargumentassignment_set.all()

    for assignment in list(executable_args) + list(spell_args):
        raw_arg = assignment.argument.argument.strip()
        resolved_arg = _render_text(raw_arg, render_ctx)
        ordered_arguments_list.append(resolved_arg)

    executable_switches = spell.talos_executable.switches.all()
    spell_switches = spell.switches.all()

    switch_list = []

    for switch in list(executable_switches) + list(spell_switches):
        flag = switch.flag.strip()
        value = switch.value.strip() if switch.value else ''

        exec_item = _render_text(flag + value, render_ctx)
        switch_list.append(exec_item)

    return ordered_arguments_list + switch_list
