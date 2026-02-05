"""Views for the dashboard application."""

import os

from celery.result import AsyncResult
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import TemplateView

from config.celery import app as celery_app
from core.tasks import scan_network_task
from dashboard.tasks import debug_task
from hydra.models import (
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)
from talos_agent.version import VERSION as SERVER_VERSION


def serialize_spawn_helper(spawn):
    """
    Serializes a spawn using the Model's native properties.
    Refactored to rely on 'live_heads' and 'finished_heads' exclusively.
    """

    # 1. Fetch via Model Properties
    # Use select_related to prevent N+1 queries during template iteration
    live = spawn.live_heads.select_related(
        'spell', 'target', 'status'
    ).order_by('created')
    history = spawn.finished_heads.select_related(
        'spell', 'target', 'status'
    ).order_by('created')

    # 2. Resolve Children (Sub-graphs)
    # Using the model properties here as well for consistency
    children = list(spawn.live_head_spawns) + list(spawn.finished_head_spawns)
    children.sort(key=lambda x: x.created)

    return {
        'object': spawn,
        # Native Model Properties (Status Flags)
        'is_alive': spawn.is_alive,
        'is_dead': spawn.is_dead,
        'is_stopping': spawn.is_stopping,
        'ended_badly': spawn.ended_badly,
        'ended_successfully': spawn.ended_successfully,
        # Recursion
        'subgraphs': [serialize_spawn_helper(child) for child in children],
        # Data Streams
        # 'live_children' now holds ALL active heads (Created, Pending, Running).
        # The template can differentiate styles using head.is_queued if needed.
        'live_children': list(live),
        'history': list(history),
        # Explicitly empty 'pending' to deprecate its usage in the template logic
        'pending': [],
    }


class DashboardHomeView(TemplateView):
    template_name = 'dashboard/mission_control.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 1. Fetch all books with tags
        all_books = HydraSpellbook.objects.prefetch_related('tags').order_by(
            'name'
        )

        # 2. Partition
        favorites = []
        tagged_groups = {}  # { "TagName": [book1, book2] }
        uncategorized = []

        for book in all_books:
            if book.is_favorite:
                favorites.append(book)

            # If tags exist, add to groups
            tags = book.tags.all()
            if tags:
                for tag in tags:
                    if tag.name not in tagged_groups:
                        tagged_groups[tag.name] = []
                    tagged_groups[tag.name].append(book)
            else:
                uncategorized.append(book)

        # 3. Sort Groups Alphabetically
        sorted_groups = []
        for tag_name in sorted(tagged_groups.keys()):
            sorted_groups.append(
                {'name': tag_name, 'books': tagged_groups[tag_name]}
            )

        context['favorites'] = favorites
        context['tagged_groups'] = sorted_groups
        context['uncategorized'] = uncategorized

        # --- SPAWN MONITOR LOGIC ---
        root_spawns = HydraSpawn.objects.filter(
            parent_head__isnull=True
        ).order_by('-created')[:20]

        lanes = []
        is_system_active = False  # Track if we need to keep polling

        for spawn in root_spawns:
            serialized = self._serialize_spawn(spawn)
            if serialized['is_alive']:
                is_system_active = True
            lanes.append(serialized)

        context['lanes'] = lanes
        context['is_system_active'] = is_system_active
        return context

    def _serialize_spawn(self, spawn):
        return serialize_spawn_helper(spawn)


class SwimlanePartialView(View):
    """Renders a single swimlane for HTMX polling."""

    def get(self, request, pk, *args, **kwargs):
        spawn = get_object_or_404(HydraSpawn, pk=pk)
        serialized_lane = serialize_spawn_helper(spawn)
        return render(
            request,
            'dashboard/partials/mission_swimlane.html',
            {'lane': serialized_lane},
        )


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
