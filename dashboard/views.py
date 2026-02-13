import logging

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView

from environments.models import ProjectEnvironment
from hydra.models import HydraSpawn, HydraSpellbook
from hydra.serializers import HydraSwimlaneSerializer

logger = logging.getLogger(__name__)


class DashboardHomeView(TemplateView):
    template_name = 'dashboard/mission_control.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        envs = list(ProjectEnvironment.objects.all().order_by('name'))
        active_env = next((e for e in envs if e.selected), None)
        context['environments'] = envs
        context['active_environment'] = active_env

        # Base querysets
        spawn_qs = HydraSpawn.objects.filter(parent_head__isnull=True)

        if active_env:
            all_books = (
                HydraSpellbook.objects.filter(
                    Q(environment=active_env) | Q(environment__isnull=True)
                )
                .prefetch_related('tags')
                .order_by('name')
            )
            spawn_qs = spawn_qs.filter(environment=active_env)
        else:
            all_books = HydraSpellbook.objects.prefetch_related(
                'tags'
            ).order_by('name')

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

        sorted_groups = [
            {'name': k, 'books': v} for k, v in sorted(tagged_groups.items())
        ]

        context['favorites'] = favorites
        context['tagged_groups'] = sorted_groups
        context['uncategorized'] = uncategorized

        # Fetch Active Missions using the safe query
        root_spawns = spawn_qs.select_related(
            'status', 'spellbook', 'environment'
        ).order_by('-created')[:20]

        lanes = []
        is_system_active = False

        for spawn in root_spawns:
            serialized = HydraSwimlaneSerializer(spawn).data

            # TEMPLATE COMPATIBILITY INJECTIONS:
            # Provide the raw object on both keys so the legacy template can find
            # things like {{ lane.spawn.id }} or {{ lane.object.status.name }}
            serialized['spawn'] = spawn
            serialized['object'] = spawn

            if serialized.get('is_alive'):
                is_system_active = True
            lanes.append(serialized)

        context['lanes'] = lanes
        context['is_system_active'] = is_system_active
        return context


class SwimlanePartialView(View):
    """Renders a single swimlane for HTMX polling."""

    def get(self, request, pk, *args, **kwargs):
        target_dom_id = f'lane-wrapper-{pk}'

        try:
            spawn = get_object_or_404(HydraSpawn, pk=pk)

            serialized_lane = HydraSwimlaneSerializer(spawn).data
            # TEMPLATE COMPATIBILITY INJECTIONS
            serialized_lane['spawn'] = spawn
            serialized_lane['object'] = spawn

            html = render_to_string(
                'dashboard/partials/mission_swimlane.html',
                {'lane': serialized_lane},
                request=request,
            ).strip()

            if f'id="{target_dom_id}"' not in html:
                html = f'<div class="lane-wrapper" id="{target_dom_id}">{html}</div>'

            return HttpResponse(html, content_type='text/html')

        except Exception as e:
            logger.error(f'Swimlane View Fatal Error: {e}', exc_info=True)
            return HttpResponse(
                f'<div class="lane-wrapper" id="{target_dom_id}">'
                f'<div class="swimlane failed-lane" style="padding: 20px; border: 1px solid red; color: #ef4444;">'
                f'<strong>SYNC ERROR:</strong> {str(e)}</div></div>',
                status=200,
                content_type='text/html',
            )


# TODO: REMOVE
class ShutdownView(View):
    def post(self, request, *args, **kwargs):
        print('System-wide shutdown initiated from dashboard...')
        from config.celery import app as celery_app

        try:
            celery_app.control.shutdown()
        except Exception as e:
            print(f'Warning: Could not broadcast Celery shutdown: {e}')
        import os

        os._exit(0)
        return HttpResponse('System Offline')
