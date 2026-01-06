'''Celery tasks for the Talos Agent application.'''

from celery import shared_task
from django.utils import timezone
from core.models import RemoteTarget
from talos_agent.models import AgentTelemetry, AgentEvent
from talos_agent.utils.client import TalosAgentClient

@shared_task
def collect_agent_telemetry_task():
  '''Periodic task to poll metrics from all online agents.'''
  targets = RemoteTarget.objects.filter(status='ONLINE')
  
  for target in targets:
    client = TalosAgentClient(target.ip_address, port=target.agent_port)
    # Note: Using a generic 'HSHVacancy' or similar project name from config level in future
    status_res = client.get_status(project='HSHVacancy')
    
    if status_res.get('status') == 'OK':
      data = status_res.get('data', {})
      metrics = data.get('metrics', {})
      
      AgentTelemetry.objects.create(
          target=target,
          cpu_usage=metrics.get('cpu_percent', 0.0),
          memory_usage_mb=metrics.get('memory_mb', 0.0),
          is_functioning=data.get('functioning', False),
          is_alive=data.get('alive', False),
          raw_payload=data
      )
    else:
      # If status check fails but we thought it was online, log event
      AgentEvent.objects.create(
          target=target,
          event_type='DISCONNECT',
          message='Failed to reach agent during telemetry collection.'
      )
      target.status = 'OFFLINE'
      target.save()

  return f'Telemetry collected for {targets.count()} agents.'
