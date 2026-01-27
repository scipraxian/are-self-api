from typing import List

from django.template import Context, Template

from hydra.models import HydraSpell


def _render_text(text: str, render_ctx: Context) -> str:
    """
    Helper to render a string using Django's template engine.
    Returns the original text if no template tags are found.
    """
    if not text:
        return ''
    # Performance: Skip the engine if no templating is needed
    if '{{' not in text:
        return text
    return Template(text).render(render_ctx)


def spell_switches_and_arguments(
    spell_id: int, context: dict = None
) -> List[str]:
    """
    Resolve the arguments and switches for the spell.

    Args:
        spell_id: The ID of the spell to resolve.
        context: Runtime variables (e.g., {'target': '192.168.1.100'})

    Returns:
        Ordered list of resolved [arguments] + [switches]
    """
    # OPTIMIZATION: Single query with prefetch to avoid N+1 DB hits
    spell = (
        HydraSpell.objects.select_related('talos_executable')
        .prefetch_related(
            # Prefetch arguments and their definitions
            'talos_executable__talosexecutableargumentassignment_set__argument',
            'hydraspellargumentassignment_set__argument',
            # Prefetch switches
            'talos_executable__switches',
            'switches',
        )
        .get(id=spell_id)
    )

    # Prepare Context
    render_ctx = Context(context or {})

    # 1. Process Arguments
    # Note: We rely on the order defined in the DB or default sorting
    executable_args = (
        spell.talos_executable.talosexecutableargumentassignment_set.all()
    )
    spell_args = spell.hydraspellargumentassignment_set.all()

    ordered_arguments_list = []

    # Combine executable args + spell args
    for assignment in list(executable_args) + list(spell_args):
        # assignment.argument -> The Argument Definition Model
        # assignment.argument.argument -> The actual string value
        raw_arg = assignment.argument.argument.strip()

        resolved_arg = _render_text(raw_arg, render_ctx)
        ordered_arguments_list.append(resolved_arg)

    # 2. Process Switches
    executable_switches = spell.talos_executable.switches.all()
    spell_switches = spell.switches.all()

    switch_list = []

    for switch in list(executable_switches) + list(spell_switches):
        flag = switch.flag.strip()
        value = switch.value.strip() if switch.value else ''

        # Render the combined string to handle cases like /DIR:{{ target }}\Logs
        exec_item = _render_text(flag + value, render_ctx)

        switch_list.append(exec_item)

    return ordered_arguments_list + switch_list
