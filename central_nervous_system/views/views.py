import json

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from central_nervous_system.models import Spike, SpikeTrain
from central_nervous_system.utils import (
    get_active_environment,
    resolve_environment_context,
)


def _truncate_log(log_text, max_lines=20):
    """Truncates a log to max_lines, showing head and a line count summary."""
    if not log_text:
        return '<No Output>'
    lines = log_text.splitlines()
    total = len(lines)
    if total <= max_lines:
        return log_text
    head = '\n'.join(lines[:max_lines])
    return f'{head}\n... ({total - max_lines} more lines, {total} total)'


def generate_spawn_dump(spike_train, depth=0, summary=False):
    """Generator that streams the execution context of a SpikeTrain and its subgraphs.

    Args:
        spike_train: The SpikeTrain instance to dump.
        depth: Current recursion depth (for indentation).
        summary: If True, truncates logs and axoplasm for reviewable output.
    """
    indent = '    ' * depth

    yield f'{indent}SPAWN EXPORT {"(SUBGRAPH)" if depth > 0 else ""}{"  [SUMMARY]" if summary and depth == 0 else ""}\n'
    yield f'{indent}================================================================================\n'
    yield f'{indent}SpikeTrain ID:   {spike_train.id}\n'
    yield f'{indent}NeuralPathway:  {spike_train.pathway.name if spike_train.pathway else "Deleted"}\n'
    yield f'{indent}Status:     {spike_train.status.name}\n'
    yield f'{indent}Created:    {spike_train.created}\n'
    yield f'{indent}Environment: {spike_train.environment.name if spike_train.environment else "None"}\n'
    yield f'{indent}================================================================================\n\n'

    # Fetch all spikes in order
    spikes = (
        spike_train.spikes.all()
        .order_by('created')
        .select_related(
            'effector', 'status', 'target', 'neuron', 'effector__executable'
        )
    )

    for i, spike in enumerate(spikes):
        yield f'{indent}--- HEAD #{i + 1} [{spike.id}] ---\n'
        yield f'{indent}Spell:      {spike.effector.name if spike.effector else "None"}\n'
        yield f'{indent}Status:     {spike.status.name}\n'
        yield f'{indent}Target:     {spike.target.hostname if spike.target else "Local Server"}\n'

        # Resolve the command string for context
        cmd_str = 'Command resolution failed'
        try:
            env = get_active_environment(spike)
            ctx = resolve_environment_context(spike_id=spike.id)
            if spike.effector:
                full_cmd = spike.effector.get_full_command(
                    environment=env, extra_context=ctx
                )
                cmd_str = ' '.join(full_cmd)
            else:
                cmd_str = '<No Effector Attached>'
        except Exception as e:
            cmd_str = f'<Error: {e}>'

        yield f'{indent}Command:    {cmd_str}\n'
        yield f'{indent}Result RC:  {spike.result_code}\n'

        # Output the Axoplasm state
        if spike.axoplasm:
            bb_text = json.dumps(spike.axoplasm)
            if summary and len(bb_text) > 500:
                bb_text = bb_text[:500] + f'... ({len(bb_text)} chars total)'
            yield f'{indent}Axoplasm: {bb_text}\n'

        yield f'\n{indent}[SPELL LOG (Tool Output)]\n'
        yield f'{indent}-------------------------\n'
        if summary:
            yield _truncate_log(spike.application_log, max_lines=20)
        else:
            yield spike.application_log if spike.application_log else '<No Output>'
        yield '\n'

        yield f'\n{indent}[EXECUTION LOG (System)]\n'
        yield f'{indent}------------------------\n'
        if summary:
            yield _truncate_log(spike.execution_log, max_lines=10)
        else:
            yield spike.execution_log if spike.execution_log else '<No System Logs>'
        yield '\n'
        yield '\n'
        yield f'{indent}================================================================================\n\n'
        child_trains = spike.child_trains.all().order_by('created')
        for child in child_trains:
            yield from generate_spawn_dump(child, depth + 1, summary=summary)


class SpikeTrainDownloadView(View):
    """Streams all data from a spike_train into a single .log file download."""

    def get(self, request, pk):
        spike_train = get_object_or_404(SpikeTrain, pk=pk)
        summary = request.GET.get('summary', 'false').lower() == 'true'

        response = StreamingHttpResponse(
            generate_spawn_dump(spike_train, summary=summary),
            content_type='text/plain',
        )

        mode_tag = '_summary' if summary else ''
        filename = f'Spawn_{str(spike_train.id)[:8]}_{spike_train.status.name}{mode_tag}.log'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
