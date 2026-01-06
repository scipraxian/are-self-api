'''Views for the Talos Agent application.'''

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.generic import DetailView
from core.models import RemoteTarget
from talos_agent.models import AgentTelemetry, AgentEvent
from talos_agent.utils.client import TalosAgentClient
from core.utils.config_manager import load_builder_config
from talos_agent.version import VERSION as SERVER_VERSION

class AgentDetailView(DetailView):
  '''Drill-down view for a specific build agent.'''
  model = RemoteTarget
  template_name = 'talos_agent/agent_detail.html'
  context_object_name = 'agent'

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['latest_telemetry'] = self.object.telemetry.first()
    context['recent_events'] = self.object.events.all()[:10]
    context['server_version'] = SERVER_VERSION
    return context

def agent_live_metrics_partial(request, pk):
  '''HTMX partial that actively queries the agent for real-time data.'''
  agent = get_object_or_404(RemoteTarget, pk=pk)
  config = load_builder_config()
  pname = config.get('ProjectName', 'HSHVacancy')
  
  client = TalosAgentClient(agent.ip_address, port=agent.agent_port, timeout=1.0)
  res = client.get_status(pname, log_path=agent.remote_log_path)
  
  metrics_data = None
  error_msg = None

  if res.get('status') == 'OK':
    data = res.get('data', {})
    
    metrics_data = AgentTelemetry.objects.create(
        target=agent,
        cpu_usage=data.get('cpu', 0.0),
        memory_usage_mb=data.get('ram_mb', 0.0),
        is_functioning=data.get('functioning', False),
        is_alive=data.get('alive', False),
        storage_ok=agent.is_exe_available,
        storage_info=f"Exe: {'READY' if agent.is_exe_available else 'NOT_FOUND'}",
        raw_payload=res
    )
    if agent.status in ['OFFLINE', 'STORAGE_ERROR']:
      agent.status = 'ONLINE'
    
    # Capture version from handshake
    if res.get('version'):
        agent.version = res.get('version')
        
    agent.save()
  else:
    error_msg = res.get('message', 'Connection Failed')
    metrics_data = agent.telemetry.first()

  return render(request, 'talos_agent/partials/metrics_card.html', {
      'agent': agent,
      'metrics': metrics_data,
      'error': error_msg,
      'server_version': SERVER_VERSION
  })

def agent_launch_view(request, pk):
  agent = get_object_or_404(RemoteTarget, pk=pk)
  if not agent.is_exe_available:
    return JsonResponse({'status': 'ERROR', 'message': 'Exe not located yet.'})
    
  client = TalosAgentClient(agent.ip_address, port=agent.agent_port)
  # Ensure -AutoStart and windowed flags are passed
  res = client.launch(agent.remote_exe_path, params=['-AutoStart', '-log', '-windowed', '-resX=1280', '-resY=720'])
  
  if res.get('status') == 'LAUNCHED':
    AgentEvent.objects.create(target=agent, event_type='LAUNCH', message=f"Launched {agent.remote_exe_path}")
    return render(request, 'talos_agent/partials/control_response.html', {'message': 'Process Launched!'})
  return render(request, 'talos_agent/partials/control_response.html', {'error': res.get('message', 'Launch failed')})

def agent_kill_view(request, pk):
  agent = get_object_or_404(RemoteTarget, pk=pk)
  config = load_builder_config()
  pname = config.get('ProjectName', 'HSHVacancy')
  
  client = TalosAgentClient(agent.ip_address, port=agent.agent_port)
  res = client.kill(pname)
  
  if res.get('status') in ['KILLED', 'NOT_FOUND']:
    msg = f"Stopped {pname}.exe gracefully." if res.get('status') == 'KILLED' else f"{pname}.exe was not running."
    AgentEvent.objects.create(target=agent, event_type='KILL', message=msg)
    return render(request, 'talos_agent/partials/control_response.html', {'message': msg})
  return render(request, 'talos_agent/partials/control_response.html', {'error': f'Process {pname} kill failed: {res.get("message")}'})

def agent_logs_view(request, pk):
  '''Returns the log viewer container partial.'''
  agent = get_object_or_404(RemoteTarget, pk=pk)
  return render(request, 'talos_agent/partials/log_viewer.html', {'agent': agent})

def agent_log_feed_view(request, pk):
  '''Returns the actual log lines tail.'''
  agent = get_object_or_404(RemoteTarget, pk=pk)
  if not agent.remote_log_path:
    return render(request, 'talos_agent/partials/log_lines.html', {'lines': ['Log path not discovered yet.']})
    
  client = TalosAgentClient(agent.ip_address, port=agent.agent_port)
  res = client.tail(agent.remote_log_path, lines=100)
  
  lines = res.get('data', [])
  if res.get('status') == 'NOT_FOUND':
    lines = [f"Log file not found at expected location: {agent.remote_log_path}"]
    
  return render(request, 'talos_agent/partials/log_lines.html', {'lines': lines})

def agent_update_view(request, pk):
  '''Reads the local agent_service.py and pushes it to the remote agent.'''
  agent = get_object_or_404(RemoteTarget, pk=pk)
  
  # Read local source
  import os
  from django.conf import settings
  source_path = os.path.join(settings.BASE_DIR, 'talos_agent', 'bin', 'agent_service.py')
  
  try:
    with open(source_path, 'r') as f:
      content = f.read()
  except Exception as e:
    return render(request, 'talos_agent/partials/control_response.html', {'error': f"Failed to read local source: {e}"})

  client = TalosAgentClient(agent.ip_address, port=agent.agent_port)
  res = client.update_agent(content)
  
  if res.get('status') == 'UPDATING':
     AgentEvent.objects.create(target=agent, event_type='UPDATE', message="Agent updating self to v2.1.2.")
     return render(request, 'talos_agent/partials/control_response.html', {'message': 'Update sent! Agent restarting...'})
  
  return render(request, 'talos_agent/partials/control_response.html', {'error': res.get('message', 'Update failed')})

