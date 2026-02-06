import logging
import os

from celery.result import AsyncResult
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView

from config.celery import app as celery_app
from core.tasks import scan_network_task
from dashboard.tasks import debug_task
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)
from talos_agent.version import VERSION as SERVER_VERSION

logger = logging.getLogger(__name__)


def serialize_spawn_helper(spawn):
    """
    Serializes a spawn using native Model Properties.
    Refactored for robustness against race conditions and missing relations.
    """
    try:
        # 1. Fetch Data via Properties (Optimized)
        live_heads = list(
            spawn.live_heads.select_related(
                'spell', 'target', 'status'
            ).order_by('created')
        )

        finished_heads = list(
            spawn.finished_heads.select_related(
                'spell', 'target', 'status'
            ).order_by('created')
        )

        # 2. Handle Children (Sub-graphs)
        children = []
        try:
            children = list(spawn.live_head_spawns) + list(
                spawn.finished_head_spawns
            )
            children.sort(key=lambda x: x.created if x.created else x.modified)
        except Exception as e:
            logger.warning(
                f'Error resolving subgraphs for Spawn {spawn.id}: {e}'
            )

        return {
            'object': spawn,
            'is_alive': spawn.is_alive,
            'is_dead': spawn.is_dead,
            'is_stopping': spawn.is_stopping,
            'ended_badly': spawn.ended_badly,
            'ended_successfully': spawn.ended_successfully,
            'subgraphs': [serialize_spawn_helper(child) for child in children],
            'live_children': live_heads,
            'history': finished_heads,
            'pending': [],
        }
    except Exception as e:
        logger.error(
            f'Serialization Failed for Spawn {spawn.id}: {e}', exc_info=True
        )
        return {
            'object': spawn,
            'is_alive': False,
            'live_children': [],
            'history': [],
            'subgraphs': [],
            'error': str(e),
        }


class DashboardHomeView(TemplateView):
    template_name = 'dashboard/mission_control.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        all_books = HydraSpellbook.objects.prefetch_related('tags').order_by(
            'name'
        )

        favorites = []
        tagged_groups = {}
        uncategorized = []

        for book in all_books:
            if book.is_favorite:
                favorites.append(book)
            tags = book.tags.all()
            if tags:
                for tag in tags:
                    if tag.name not in tagged_groups:
                        tagged_groups[tag.name] = []
                    tagged_groups[tag.name].append(book)
            else:
                uncategorized.append(book)

        sorted_groups = []
        for tag_name in sorted(tagged_groups.keys()):
            sorted_groups.append(
                {'name': tag_name, 'books': tagged_groups[tag_name]}
            )

        context['favorites'] = favorites
        context['tagged_groups'] = sorted_groups
        context['uncategorized'] = uncategorized

        root_spawns = (
            HydraSpawn.objects.filter(parent_head__isnull=True)
            .select_related('status', 'spellbook')
            .prefetch_related('heads', 'heads__status', 'heads__spell')
            .order_by('-created')[:20]
        )

        lanes = []
        is_system_active = False

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
        try:
            spawn = get_object_or_404(HydraSpawn, pk=pk)
            serialized_lane = serialize_spawn_helper(spawn)

            # [FIX] Always render the template. Do NOT return raw HTML.
            html = render_to_string(
                'dashboard/partials/mission_swimlane.html',
                {'lane': serialized_lane},
                request=request,
            )
            return HttpResponse(html)

        except Exception as e:
            logger.error(f'Swimlane View Fatal Error: {e}', exc_info=True)
            # Last resort fallback: Return a valid wrapper ID to prevent HTMX swap failure,
            # but with a visible error.
            return HttpResponse(
                f'<div class="lane-wrapper" id="lane-wrapper-{pk}"><div class="swimlane failed-lane" style="padding: 20px; border: 1px solid red;"><strong>CRITICAL VIEW ERROR:</strong> {str(e)}</div></div>',
                status=200,
            )


class TriggerBuildView(View):
    def post(self, request, *args, **kwargs):
        task = debug_task.delay()
        return render(
            request,
            'dashboard/partials/build_button_queued.html',
            {'task_id': task.id},
        )


class BuildStatusView(View):
    def get(self, request, task_id, *args, **kwargs):
        result = AsyncResult(task_id)
        if result.ready():
            return render(request, 'dashboard/partials/build_button_idle.html')
        return render(
            request,
            'dashboard/partials/build_button_queued.html',
            {'task_id': task_id},
        )


class ScanNetworkView(View):
    def post(self, request, *args, **kwargs):
        scan_network_task.delay()
        return HttpResponse("""
        <div class="scanning-toast">
            Scanner Active...
        </div>
    """)


class DeleteAgentView(View):
    def delete(self, request, pk, *args, **kwargs):
        return HttpResponse('Only offline agents can be deleted.', status=403)


class AgentListView(View):
    def get(self, request, *args, **kwargs):
        targets = []
        return render(
            request,
            'dashboard/partials/agent_list.html',
            {'targets': targets, 'server_version': SERVER_VERSION},
        )


class ShutdownView(View):
    def post(self, request, *args, **kwargs):
        print('System-wide shutdown initiated from dashboard...')
        try:
            celery_app.control.shutdown()
        except Exception as e:
            print(f'Warning: Could not broadcast Celery shutdown: {e}')
        os._exit(0)
        return HttpResponse('System Offline')


class NeuralStatusView(View):
    def get(self, request, *args, **kwargs):
        from talos_frontal.models import ConsciousStream

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
