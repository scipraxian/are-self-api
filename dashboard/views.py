'''Views for the dashboard application.'''

from hydra.models import HydraSpellbook, HydraSpawn, HydraSpawnStatus
from hydra.hydra import Hydra
import os

from celery.result import AsyncResult
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from config.celery import app as celery_app
from core.models import RemoteTarget
from core.tasks import scan_network_task
from dashboard.tasks import debug_task
from talos_agent.version import VERSION as SERVER_VERSION


class DashboardHomeView(TemplateView):
  '''Renders the main dashboard page.'''
  template_name = 'dashboard/home.html'

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['targets'] = RemoteTarget.objects.all()
    context['server_version'] = SERVER_VERSION
    context['hydra_spellbooks'] = HydraSpellbook.objects.all().order_by('name')
    
    # Check for any active Hydra Spawn
    active_spawn = HydraSpawn.objects.filter(
        status_id__in=[
            HydraSpawnStatus.CREATED, 
            HydraSpawnStatus.PENDING, 
            HydraSpawnStatus.RUNNING
        ]
    ).order_by('-created').first()
    
    if active_spawn:
        # Nudge state machine to catch any finished runs or zombies
        try:
            controller = Hydra(spawn_id=active_spawn.id)
            controller.poll()
            active_spawn.refresh_from_db()
            if not active_spawn.is_active:
                active_spawn = None
        except Exception:
            # If for some reason Hydra initialization fails, don't crash the dashboard
            pass

    if active_spawn:
        context['active_spawn'] = active_spawn
        context['spawn'] = active_spawn
        context['heads'] = active_spawn.heads.all().order_by('spell__order')
        context['is_active'] = active_spawn.is_active
    else:
        context['active_spawn'] = None

    return context


class TriggerBuildView(View):
  '''Triggers a Celery task and returns an HTML fragment.'''

  def post(self, request, *args, **kwargs):
    '''Handles POST requests to trigger a build.'''
    task = debug_task.delay()
    return render(
        request,
        'dashboard/partials/build_button_queued.html',
        {'task_id': task.id},
    )


class BuildStatusView(View):
  '''Checks the status of a Celery task and returns appropriate HTML.'''

  def get(self, request, task_id, *args, **kwargs):
    '''Returns idle button if task is ready, else continues polling.'''
    result = AsyncResult(task_id)
    if result.ready():
      return render(request, 'dashboard/partials/build_button_idle.html')

    return render(
        request,
        'dashboard/partials/build_button_queued.html',
        {'task_id': task_id},
    )


class ScanNetworkView(View):
  '''Triggers the network scan task.'''

  def post(self, request, *args, **kwargs):
    '''Initiates the async scan.'''
    scan_network_task.delay()
    return HttpResponse('''
        <div class="scanning-toast">
            Scanner Active...
        </div>
    ''')


class DeleteAgentView(View):
  '''Removes a build agent from the registry.'''

  def delete(self, request, pk, *args, **kwargs):
    '''Deletes an offline agent.'''
    target = get_object_or_404(RemoteTarget, pk=pk)
    if target.status == 'OFFLINE':
      target.delete()
      return HttpResponse('')  # Remove element from UI
    return HttpResponse('Only offline agents can be deleted.', status=403)


class AgentListView(View):
  '''Returns the partial agent list for polling.'''

  def get(self, request, *args, **kwargs):
    targets = RemoteTarget.objects.all()
    return render(
        request,
        'dashboard/partials/agent_list.html',
        {'targets': targets, 'server_version': SERVER_VERSION}
    )


class ShutdownView(View):
  '''System-wide shutdown for all Talos processes.'''

  def post(self, request, *args, **kwargs):
    '''Triggers system-wide shutdown.'''
    print('System-wide shutdown initiated from dashboard...')
    try:
      celery_app.control.shutdown()
    except Exception as e:
      print(f'Warning: Could not broadcast Celery shutdown: {e}')
    os._exit(0)
    return HttpResponse('System Offline')
