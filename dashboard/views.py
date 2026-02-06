import logging
import os

from celery.result import AsyncResult
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView

from config.celery import app as celery_app
from core.tasks import scan_network_task
from dashboard.tasks import debug_task
from hydra.models import (
    HydraSpawn,
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
        live_heads = []
        try:
            live_heads = list(spawn.live_heads.all().order_by('created'))
        except Exception as e:
            logger.warning(f'Error fetching live_heads for {spawn.id}: {e}')

        finished_heads = []
        try:
            finished_heads = list(
                spawn.finished_heads.all().order_by('created')
            )
        except Exception as e:
            logger.warning(f'Error fetching finished_heads for {spawn.id}: {e}')

        # 2. Handle Children (Sub-graphs)
        children = []
        try:
            # Safely fetch children
            lhs = []
            try:
                lhs = list(spawn.live_head_spawns)
            except Exception:
                pass

            fhs = []
            try:
                fhs = list(spawn.finished_head_spawns)
            except Exception:
                pass

            children = lhs + fhs
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
    """
    Renders a single swimlane for HTMX polling.
    CRITICAL: Enforces that the returned HTML *always* contains the
    lane-wrapper-{pk} ID. If missing, it injects it to prevent the
    DOM node from vanishing during the outerHTML swap.
    """

    def get(self, request, pk, *args, **kwargs):
        # 1. Determine the exact ID that MUST be present to survive the swap
        target_dom_id = f'lane-wrapper-{pk}'

        try:
            spawn = get_object_or_404(HydraSpawn, pk=pk)
            serialized_lane = serialize_spawn_helper(spawn)

            # 2. Render Template
            html = render_to_string(
                'dashboard/partials/mission_swimlane.html',
                {'lane': serialized_lane},
                request=request,
            )
            html = html.strip()

            if not html:
                raise ValueError('Rendered HTML was empty')

            # 3. ID INTEGRITY CHECK
            # If the ID is missing (e.g. bad context), the node will lose its
            # identity and "vanish" from future selectors/polls.
            if target_dom_id not in html:
                logger.critical(
                    f'Swimlane partial missing ID {target_dom_id}. Injecting fallback wrapper.'
                )
                # Auto-Recovery: Wrap the content in the correct ID so the UI persists
                html = f'<div class="lane-wrapper" id="{target_dom_id}">{html}</div>'

            return HttpResponse(html, content_type='text/html')

        except Exception as e:
            logger.error(f'Swimlane View Fatal Error: {e}', exc_info=True)
            # 4. FAILSAFE RETURN
            # Return a valid wrapper matching the ID so the UI updates to show error
            # instead of deleting the node.
            return HttpResponse(
                f'<div class="lane-wrapper" id="{target_dom_id}">'
                f'<div class="swimlane failed-lane" style="padding: 20px; border: 1px solid red;">'
                f'<strong>SYNC ERROR:</strong> {str(e)}</div></div>',
                status=200,
                content_type='text/html',
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
