import json

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from central_nervous_system.models import Spike, SpikeTrain
from central_nervous_system.utils import (
    get_active_environment,
    resolve_environment_context,
)


def generate_spawn_dump(spike_train, depth=0):
    """Generator that streams the entire execution context of a SpikeTrain and its subgraphs."""
    indent = '    ' * depth

    yield f'{indent}SPAWN EXPORT {"(SUBGRAPH)" if depth > 0 else ""}\n'
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
            'effector', 'status', 'target', 'neuron', 'spell__talos_executable'
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

        # Output the exact Blackboard state!
        if spike.blackboard:
            yield f'{indent}Blackboard: {json.dumps(spike.blackboard)}\n'

        yield f'\n{indent}[SPELL LOG (Tool Output)]\n'
        yield f'{indent}-------------------------\n'
        if spike.application_log:
            yield spike.application_log
        else:
            yield '<No Output>'
        yield '\n'

        yield f'\n{indent}[EXECUTION LOG (System)]\n'
        yield f'{indent}------------------------\n'
        if spike.execution_log:
            yield spike.execution_log
        else:
            yield '<No System Logs>'
        yield '\n'
        yield '\n'
        yield f'{indent}================================================================================\n\n'
        child_trains = spike.child_trains.all().order_by('created')
        for child in child_trains:
            yield from generate_spawn_dump(child, depth + 1)


class SpikeTrainDownloadView(View):
    """Streams all data from a spike_train into a single .log file download."""

    def get(self, request, pk):
        spike_train = get_object_or_404(SpikeTrain, pk=pk)

        response = StreamingHttpResponse(
            generate_spawn_dump(spike_train), content_type='text/plain'
        )

        filename = f'Spawn_{str(spike_train.id)[:8]}_{spike_train.status.name}.log'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
