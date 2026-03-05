from identity.addons.addon_package import AddonPackage
from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask
from temporal_lobe.models import Iteration


def agile_addon(package: AddonPackage) -> str:
    """
    Identity Addon: Dynamically injects the active Agile Board context into the system prompt.
    Adapts the ticket payload based on the current Temporal Shift (Grooming, Planning, Executing).
    """
    iteration_id = package.iteration

    if not iteration_id:
        return '[AGILE CONTEXT: Unattached / Free Roam. No active iteration.]'

    try:
        iteration = Iteration.objects.select_related(
            'current_shift__shift'
        ).get(id=iteration_id)
        shift = iteration.current_shift
    except Iteration.DoesNotExist:
        return '[AGILE CONTEXT: ERROR - Iteration not found.]'

    if not shift or not shift.shift:
        return '[AGILE CONTEXT: Awaiting Shift Assignment]'

    shift_name = shift.shift.name.upper()

    context_lines = [
        '=========================================',
        f' AGILE BOARD CONTEXT | SHIFT: {shift_name}',
        '=========================================',
    ]

    # GROOMING: Focus on High-Level Epics
    if shift_name == 'GROOMING':
        epics = PFCEpic.objects.exclude(
            status__name__in=['Done', 'Will not do.']
        )[:3]
        if not epics:
            context_lines.append('No active Epics require grooming.')
        for epic in epics:
            context_lines.append(f'\n[EPIC ID: {epic.id}] {epic.name}')
            context_lines.append(f'Description: {epic.description}')
            context_lines.append(f'Perspective (Who/Why): {epic.perspective}')
            context_lines.append(
                '-> DIRECTIVE: Groom this Epic. Break it down into strictly formatted Stories using mcp_ticket.'
            )

    # PLANNING: Focus on creating Tasks for Stories
    elif shift_name in ['PRE-PLANNING', 'PLANNING']:
        stories = PFCStory.objects.exclude(
            status__name__in=['Done', 'Will not do.']
        )[:5]
        if not stories:
            context_lines.append('No active Stories require planning.')
        for story in stories:
            context_lines.append(f'\n[STORY ID: {story.id}] {story.name}')
            context_lines.append(f'Perspective: {story.perspective}')
            context_lines.append(f'Assertions (DoD):\n{story.assertions}')
            context_lines.append(f'Outside (Do NOT Do):\n{story.outside}')
            context_lines.append(
                '-> DIRECTIVE: Verify DoR (Definition of Ready). Break this Story into actionable Tasks using mcp_ticket.'
            )

    # EXECUTING: Focus on tactical execution of Tasks
    elif shift_name == 'EXECUTING':
        tasks = PFCTask.objects.exclude(
            status__name__in=['Done', 'Will not do.']
        )[:5]
        if not tasks:
            context_lines.append('No active Tasks require execution.')
        for task in tasks:
            context_lines.append(f'\n[TASK ID: {task.id}] {task.name}')
            context_lines.append(f'Description: {task.description}')
            context_lines.append(
                '-> DIRECTIVE: Execute this task. Fulfill the parent story assertions. Document discoveries in Engrams. Close task when complete.'
            )

    else:
        context_lines.append(
            f"\n[Standby: No specific agile rules defined for shift type '{shift_name}'.]"
        )

    return '\n'.join(context_lines)
