'''Celery tasks for core network operations.'''

from django.utils import timezone
from celery import shared_task

from core.models import RemoteTarget
from core.utils.scanner import NetworkScanner


@shared_task
def scan_network_task():
  '''Orchestrates the network scan to discover and update build agents.'''
  scanner = NetworkScanner()
  
  # 1. Re-verify existing targets
  existing_targets = RemoteTarget.objects.all()
  for target in existing_targets:
    res = scanner.check_agent(target.ip_address)
    if res['online']:
      target.status = 'ONLINE' if res['share_ok'] else 'STORAGE_ERROR'
      target.last_seen = timezone.now()
    else:
      target.status = 'OFFLINE'
    target.save()

  # 2. Scan subnet for new agents
  found_agents = scanner.scan_subnet()

  # 3. Update or Create records for found agents
  for agent in found_agents:
    status = 'ONLINE' if agent['share_ok'] else 'STORAGE_ERROR'
    RemoteTarget.objects.update_or_create(
        ip_address=agent['ip'],
        defaults={
            'hostname': agent['hostname'],
            'status': status,
            'last_seen': timezone.now(),
            'unc_path': fr'\\{agent["ip"]}\steambuild' if agent['share_ok'] else ''
        }
    )

  return f'Scan completed. Found {len(found_agents)} active agents.'
