import logging

from django.http import HttpResponse
from django.shortcuts import redirect, render, reverse
from django.utils.html import escape
from django.views import View
from django.views.generic import DetailView

from .hydra import Hydra
from .models import HydraHead, HydraSpawn, HydraSpellbook, HydraStatusID
from .utils import merge_logs

logger = logging.getLogger(__name__)


class HydraResponseMixin:
    """Centralized UI logic for parched, DRY responses."""

    @staticmethod
    def render_hydra_controls(request, spawn=None):
        """Renders the dashboard control fragment with strict context."""
        history_limit = 5
        context = dict(
            active_spawn=spawn,
            spawn=spawn,
            spawn_history=HydraSpawn.objects.all().order_by('-created')[
                :history_limit
            ],
        )

        if spawn:
            context.update(
                dict(
                    heads=spawn.heads.all(),
                    is_active=spawn.is_active,
                )
            )
        else:
            context.update(
                dict(
                    hydra_spellbooks=HydraSpellbook.objects.all().order_by(
                        'name'
                    ),
                )
            )

        return render(request, 'dashboard/partials/hydra_button.html', context)

    def finalize_mission_response(self, request, spawn):
        """Routes HTMX fragments vs full-page redirects."""
        if request.headers.get('HX-Request'):
            return self.render_hydra_controls(request, spawn)
        return redirect(
            f'{reverse("hydra:graph_editor", kwargs={"book_id": spawn.spellbook_id})}?spawn_id={spawn.id}'
        )


class LaunchSpellbookView(HydraResponseMixin, DetailView):
    """Refactored model-based view for build orchestration."""

    model = HydraSpellbook
    pk_url_kwarg = 'spellbook_id'

    def post(self, request, *args, **kwargs):
        spellbook = self.get_object()

        # Find active missions via relationship join
        active_spawn = (
            spellbook.hydraspawn_set.filter(
                status_id__in=[
                    HydraStatusID.CREATED,
                    HydraStatusID.PENDING,
                    HydraStatusID.RUNNING,
                ]
            )
            .order_by('-created')
            .first()
        )

        if active_spawn:
            Hydra(spawn_id=active_spawn.id).poll()
            active_spawn.refresh_from_db()
            if active_spawn.is_active:
                return self.finalize_mission_response(request, active_spawn)

        try:
            controller = Hydra(spellbook_id=spellbook.id)
            controller.start()
            return self.finalize_mission_response(request, controller.spawn)
        except Exception as e:
            logger.exception('[HYDRA] Launch Failed')
            return render(
                request,
                'hydra/partials/error.html',
                dict(message=str(e)),
                status=500,
            )


class SpawnMonitorDetailView(HydraResponseMixin, DetailView):
    """High-fidelity build monitoring with automatic polling support."""

    model = HydraSpawn
    template_name = 'hydra/spawn_monitor.html'
    context_object_name = 'spawn'

    def get_context_data(self, **kwargs):
        # DetailView expects self.object to be set
        spawn = self.object or self.get_object()

        if spawn.is_active:
            try:
                # Nudge state machine
                from .hydra import Hydra

                Hydra(spawn_id=spawn.id).poll()
                spawn.refresh_from_db()
            except Exception:
                pass

        context = super().get_context_data(**kwargs)
        context.update(
            dict(
                heads=spawn.heads.all(),
                is_active=spawn.is_active,
                is_full_page=self.request.GET.get('full') == 'True',
            )
        )
        return context

    def get(self, request, *args, **kwargs):
        # Set the object immediately to satisfy DetailView requirements
        self.object = self.get_object()

        if not request.headers.get('HX-Request'):
            return render(
                request,
                'hydra/spawn_monitor_page.html',
                self.get_context_data(),
            )
        return super().get(request, *args, **kwargs)


class HeadLogDetailView(DetailView):
    """Log Viewer for Tool, System, and Neural Analysis streams."""

    model = HydraHead
    context_object_name = 'head'

    def get(self, request, *args, **kwargs):
        head = self.get_object()
        log_type = request.GET.get('type', 'tool')
        is_partial = request.GET.get('partial') == 'content'

        if log_type == 'system':
            content = head.execution_log or 'No system events logged.'
        elif log_type == 'stimulus':
            thought = head.thoughts.last()
            content = (
                thought.used_prompt if thought else 'No stimulus recorded.'
            )
        else:
            content = head.spell_log or 'Waiting for output...'

        if is_partial:
            return HttpResponse(escape(content))

        return render(
            request,
            'hydra/partials/head_log.html',
            dict(head=head, content=content, log_type=log_type),
        )


class BattleStationStreamView(DetailView):
    """Synchronized Client/Server log merging for Multiplayer Debugging."""

    model = HydraSpawn

    def get(self, request, *args, **kwargs):
        spawn = self.get_object()

        def get_cursor(key):
            try:
                val = request.GET.get(key)
                return int(val) if val and val != 'undefined' else 0
            except (ValueError, TypeError):
                return 0

        local_cursor = get_cursor('local_cursor')
        remote_cursor = get_cursor('remote_cursor')

        heads = spawn.heads.all()
        local_head = heads.filter(spell__name__icontains='Local').first()
        remote_head = heads.filter(spell__name__icontains='Remote').first()

        if not local_head or not remote_head:
            return HttpResponse(
                'Error: Local/Remote head requirements not met.', status=400
            )

        new_local = (local_head.spell_log or '')[local_cursor:]
        new_remote = (remote_head.spell_log or '')[remote_cursor:]

        if not new_local and not new_remote:
            return HttpResponse('', status=204)

        merged_events = merge_logs(new_local, new_remote)

        return render(
            request,
            'hydra/partials/battle_stream.html',
            dict(
                events=merged_events,
                new_local_cursor=local_cursor + len(new_local),
                new_remote_cursor=remote_cursor + len(new_remote),
                spawn=spawn,
            ),
        )


class SpawnTerminateView(View):
    """Safe termination with revoke signals."""

    def post(self, request, pk):
        controller = Hydra(spawn_id=pk)
        controller.terminate()
        return HttpResponse('Session terminated.')


class HydraControlsView(HydraResponseMixin, View):
    """Simplified controls fetcher using the mixin."""

    def get(self, request):
        active_spawn = (
            HydraSpawn.objects.filter(
                status_id__in=[
                    HydraStatusID.CREATED,
                    HydraStatusID.PENDING,
                    HydraStatusID.RUNNING,
                ]
            )
            .order_by('-created')
            .first()
        )

        if active_spawn:
            try:
                Hydra(spawn_id=active_spawn.id).poll()
                active_spawn.refresh_from_db()
                if not active_spawn.is_active:
                    active_spawn = None
            except Exception:
                pass

        return self.render_hydra_controls(request, active_spawn)


class HydraGraphEditorView(DetailView):
    """
    Renders the Visual Graph Editor page.
    """

    model = HydraSpellbook
    template_name = 'hydra/graph_editor.html'
    pk_url_kwarg = 'book_id'
    context_object_name = 'spellbook'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['spellbook_id'] = self.object.id
        context['spawn_id'] = self.request.GET.get('spawn_id', '')
        return context
