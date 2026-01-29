"""Views for the dashboard application."""

import os

from celery.result import AsyncResult
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from config.celery import app as celery_app
from core.tasks import scan_network_task
from dashboard.tasks import debug_task
from hydra.models import HydraSpawn, HydraSpawnStatus, HydraSpellbook
from talos_agent.version import VERSION as SERVER_VERSION


class DashboardHomeView(TemplateView):
    """Renders the main dashboard page."""

    template_name = 'dashboard/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['targets'] = []
        context['server_version'] = SERVER_VERSION
        context['hydra_spellbooks'] = HydraSpellbook.objects.all().order_by(
            'name'
        )

        # Check for any active Hydra Spawn
        active_spawn = (
            HydraSpawn.objects.filter(
                status_id__in=[
                    HydraSpawnStatus.CREATED,
                    HydraSpawnStatus.PENDING,
                    HydraSpawnStatus.RUNNING,
                ]
            )
            .order_by('-created')
            .first()
        )

        # --- NEUTERED: No more polling or refreshing here ---
        # The frontend is now strictly read-only.
        # If the spawn is stuck, it's a backend/Celery problem.

        if active_spawn:
            context['active_spawn'] = active_spawn
            context['spawn'] = active_spawn
            context['is_active'] = active_spawn.is_active
            # --- REMOVED: context['heads'] ---
            # This hides the "Head Viewer Rows" on the main dashboard
        else:
            context['active_spawn'] = None

        context['spawn_history'] = HydraSpawn.objects.all().order_by(
            '-created'
        )[:5]

        # Version Tracking
        context['latest_stage'] = (
            HydraSpawn.objects.filter(
                spellbook__name__icontains='Stage',
                status_id=HydraSpawnStatus.SUCCESS,
            )
            .order_by('-created')
            .first()
        )

        context['latest_uat'] = (
            HydraSpawn.objects.filter(
                spellbook__name__icontains='UAT',
                status_id=HydraSpawnStatus.SUCCESS,
            )
            .order_by('-created')
            .first()
        )

        return context


class TriggerBuildView(View):
    """Triggers a Celery task and returns an HTML fragment."""

    def post(self, request, *args, **kwargs):
        """Handles POST requests to trigger a build."""
        task = debug_task.delay()
        return render(
            request,
            'dashboard/partials/build_button_queued.html',
            {'task_id': task.id},
        )


class BuildStatusView(View):
    """Checks the status of a Celery task and returns appropriate HTML."""

    def get(self, request, task_id, *args, **kwargs):
        """Returns idle button if task is ready, else continues polling."""
        result = AsyncResult(task_id)
        if result.ready():
            return render(request, 'dashboard/partials/build_button_idle.html')

        return render(
            request,
            'dashboard/partials/build_button_queued.html',
            {'task_id': task_id},
        )


class ScanNetworkView(View):
    """Triggers the network scan task."""

    def post(self, request, *args, **kwargs):
        """Initiates the async scan."""
        scan_network_task.delay()
        return HttpResponse("""
        <div class="scanning-toast">
            Scanner Active...
        </div>
    """)


class DeleteAgentView(View):
    """Removes a build agent from the registry."""

    def delete(self, request, pk, *args, **kwargs):
        """Deletes an offline agent."""
        # target = get_object_or_404(RemoteTarget, pk=pk)
        # if target.status == 'OFFLINE':
        #     target.delete()
        #     return HttpResponse('')  # Remove element from UI
        return HttpResponse('Only offline agents can be deleted.', status=403)


class AgentListView(View):
    """Returns the partial agent list for polling."""

    def get(self, request, *args, **kwargs):
        targets = []
        return render(
            request,
            'dashboard/partials/agent_list.html',
            {'targets': targets, 'server_version': SERVER_VERSION},
        )


class ShutdownView(View):
    """System-wide shutdown for all Talos processes."""

    def post(self, request, *args, **kwargs):
        """Triggers system-wide shutdown."""
        print('System-wide shutdown initiated from dashboard...')
        try:
            celery_app.control.shutdown()
        except Exception as e:
            print(f'Warning: Could not broadcast Celery shutdown: {e}')
        os._exit(0)
        return HttpResponse('System Offline')


class NeuralStatusView(View):
    """HTMX Partial for the global brain stream."""

    def get(self, request, *args, **kwargs):
        from talos_frontal.models import ConsciousStream

        # Get the absolute latest thought from the system
        latest = (
            ConsciousStream.objects.select_related('status')
            .order_by('-created')
            .first()
        )

        return render(
            request,
            'dashboard/partials/neural_monitor.html',
            {'thought': latest},
        )
