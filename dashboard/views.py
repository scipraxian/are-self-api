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
from hydra.models import (
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpellbook,
)
from talos_agent.version import VERSION as SERVER_VERSION


class DashboardHomeView(TemplateView):
    template_name = 'dashboard/mission_control.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['spellbooks'] = HydraSpellbook.objects.all().order_by('name')

        root_spawns = HydraSpawn.objects.filter(
            parent_head__isnull=True
        ).order_by('-created')[:20]

        lanes = []
        for spawn in root_spawns:
            lanes.append(self._serialize_spawn(spawn))

        context['lanes'] = lanes
        return context

    def _serialize_spawn(self, spawn):
        heads = (
            spawn.heads.all()
            .select_related('spell', 'target', 'status')
            .order_by('created')
        )
        # Filter noise
        filtered_heads = [h for h in heads if h.spell.name != 'Begin Play']

        # Determine visual state
        is_failed = spawn.status_id == HydraSpawnStatus.FAILED
        is_active = spawn.status_id in [
            HydraSpawnStatus.RUNNING,
            HydraSpawnStatus.STOPPING,
        ]

        return {
            'object': spawn,
            'is_active': is_active,
            'is_failed': is_failed,  # NEW: Flag for Red styling
            'subgraphs': [
                self._serialize_spawn(child)
                for child in HydraSpawn.objects.filter(parent_head__spawn=spawn)
            ],
            'pending': [
                h
                for h in filtered_heads
                if h.status_id
                in [HydraHeadStatus.CREATED, HydraHeadStatus.PENDING]
            ],
            'active': [
                h
                for h in filtered_heads
                if h.status_id
                in [
                    HydraHeadStatus.RUNNING,
                    HydraHeadStatus.STOPPING,
                    HydraHeadStatus.DELEGATED,
                ]
            ],
            'history': [
                h
                for h in filtered_heads
                if h.status_id
                in [
                    HydraHeadStatus.SUCCESS,
                    HydraHeadStatus.FAILED,
                    HydraHeadStatus.ABORTED,
                    HydraHeadStatus.STOPPED,
                ]
            ],
        }


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
