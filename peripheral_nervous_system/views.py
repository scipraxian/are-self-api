"""Views for the Peripheral Nervous System application."""

import os

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.generic import DetailView

from peripheral_nervous_system.models import (
    NerveTerminalEvent,
    NerveTerminalRegistry,
)
from peripheral_nervous_system.utils.client import NerveTerminalClient
from peripheral_nervous_system.version import VERSION as SERVER_VERSION

# TODO: This is all legacy agent control. Move to DRF


class AgentDetailView(DetailView):
    """Drill-down view for a specific build agent."""

    model = NerveTerminalRegistry
    template_name = 'peripheral_nervous_system/agent_detail.html'
    context_object_name = 'agent'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['latest_telemetry'] = self.object.telemetry.first()
        context['recent_events'] = self.object.events.all()[:10]
        context['server_version'] = SERVER_VERSION
        return context


def agent_launch_view(request, pk):
    agent = get_object_or_404(NerveTerminalRegistry, pk=pk)
    if not agent.is_exe_available:
        return JsonResponse(
            {'status': 'ERROR', 'message': 'Exe not located yet.'}
        )

    client = NerveTerminalClient(agent.ip_address, port=agent.agent_port)
    # Ensure -AutoStart and windowed flags are passed
    res = client.launch(
        agent.remote_exe_path,
        params=['-AutoStart', '-log', '-windowed', '-resX=1280', '-resY=720'],
    )

    if res.get('status') == 'LAUNCHED':
        NerveTerminalEvent.objects.create(
            target=agent,
            event_type='LAUNCH',
            message=f'Launched {agent.remote_exe_path}',
        )
        return render(
            request,
            'peripheral_nervous_system/partials/control_response.html',
            {'message': 'Process Launched!'},
        )
    return render(
        request,
        'peripheral_nervous_system/partials/control_response.html',
        {'error': res.get('message', 'Launch failed')},
    )


def agent_kill_view(request, pk):
    # agent = get_object_or_404(NerveTerminalRegistry, pk=pk)
    # config = load_builder_config()
    # pname = config.get('ProjectName', 'HSHVacancy')
    #
    # client = NerveTerminalClient(agent.ip_address, port=agent.agent_port)
    # res = client.kill(pname)
    #
    # if res.get('status') in ['KILLED', 'NOT_FOUND']:
    #     msg = (
    #         f'Stopped {pname}.exe gracefully.'
    #         if res.get('status') == 'KILLED'
    #         else f'{pname}.exe was not running.'
    #     )
    #     NerveTerminalEvent.objects.create(
    #         target=agent, event_type='KILL', message=msg
    #     )
    #     return render(
    #         request,
    #         'peripheral_nervous_system/partials/control_response.html',
    #         {'message': msg},
    #     )
    # return render(
    #     request,
    #     'peripheral_nervous_system/partials/control_response.html',
    #     {'error': f'Process {pname} kill failed: {res.get("message")}'},
    # )
    pass


def agent_logs_view(request, pk):
    """Returns the log viewer container partial with log list."""
    agent = get_object_or_404(NerveTerminalRegistry, pk=pk)
    logs = []

    if agent.remote_log_path:
        log_dir = os.path.dirname(agent.remote_log_path)
        client = NerveTerminalClient(agent.ip_address, port=agent.agent_port)
        res = client.list_logs(log_dir)
        if res.get('status') == 'OK':
            logs = res.get('data', [])
            logs.reverse()  # Newest first usually

    return render(
        request,
        'peripheral_nervous_system/partials/log_viewer.html',
        {
            'agent': agent,
            'logs': logs,
            'current_log': os.path.basename(agent.remote_log_path)
            if agent.remote_log_path
            else None,
        },
    )


def agent_log_feed_view(request, pk):
    """Returns the actual log lines tail."""
    agent = get_object_or_404(NerveTerminalRegistry, pk=pk)
    log_file = request.GET.get('log_file')

    target_log = agent.remote_log_path
    if log_file and agent.remote_log_path:
        log_dir = os.path.dirname(agent.remote_log_path)
        target_log = os.path.join(log_dir, log_file)

    if not target_log:
        return render(
            request,
            'peripheral_nervous_system/partials/log_lines.html',
            {'lines': ['Log path not discovered yet.']},
        )

    client = NerveTerminalClient(agent.ip_address, port=agent.agent_port)
    res = client.tail(target_log, lines=100)

    lines = res.get('data', [])
    if res.get('status') == 'NOT_FOUND':
        lines = [f'Log file not found at expected location: {target_log}']

    return render(
        request, 'peripheral_nervous_system/partials/log_lines.html', {'lines': lines}
    )


def agent_update_view(request, pk):
    """Reads the local and pushes it to the remote agent."""
    agent = get_object_or_404(NerveTerminalRegistry, pk=pk)

    # Read local source
    import os

    from django.conf import settings

    source_path = os.path.join(
        settings.BASE_DIR, 'peripheral_nervous_system', 'bin', 'invalid'
    )

    try:
        with open(source_path, 'r') as f:
            content = f.read()
    except Exception as e:
        return render(
            request,
            'peripheral_nervous_system/partials/control_response.html',
            {'error': f'Failed to read local source: {e}'},
        )

    client = NerveTerminalClient(agent.ip_address, port=agent.agent_port)
    res = client.update_agent(content)

    if res.get('status') == 'UPDATING':
        NerveTerminalEvent.objects.create(
            target=agent,
            event_type='UPDATE',
            message='Agent updating self to v2.1.3.',
        )
        return render(
            request,
            'peripheral_nervous_system/partials/control_response.html',
            {'message': 'Update sent! Agent restarting...'},
        )

    return render(
        request,
        'peripheral_nervous_system/partials/control_response.html',
        {'error': res.get('message', 'Update failed')},
    )
