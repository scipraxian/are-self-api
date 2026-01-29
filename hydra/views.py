import os

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView

from .hydra import Hydra
from .models import HydraHead, HydraSpawn, HydraSpellbook

# --- GRAPH VIEWS ---


class HydraGraphEditorView(DetailView):
    model = HydraSpellbook
    template_name = 'hydra/graph_editor.html'
    context_object_name = 'book'
    pk_url_kwarg = 'book_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mode'] = 'edit'
        context['spawn_id'] = ''
        return context


class HydraGraphMonitorView(DetailView):
    model = HydraSpawn
    template_name = 'hydra/graph_editor.html'
    context_object_name = 'spawn'
    pk_url_kwarg = 'spawn_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['book'] = self.object.spellbook
        context['mode'] = 'monitor'
        context['spawn_id'] = str(self.object.id)
        return context


class LaunchSpellbookView(View):
    """
    Launches the graph and forces a hard browser redirect.
    """

    def dispatch_launch(self, spellbook_id):
        controller = Hydra(spellbook_id=spellbook_id)
        controller.start()

        target_url = reverse(
            'hydra:graph_monitor', kwargs={'spawn_id': controller.spawn.id}
        )

        # FAIL-SAFE: Return a script tag. HTMX will execute this and redirect the whole window.
        if self.request.headers.get('HX-Request'):
            return HttpResponse(
                f"<script>window.location.href = '{target_url}';</script>"
            )

        return redirect(target_url)

    def get(self, request, spellbook_id):
        return self.dispatch_launch(spellbook_id)

    def post(self, request, spellbook_id):
        return self.dispatch_launch(spellbook_id)


class TerminateSpawnView(View):
    """
    Aborts a running Spawn.
    """

    def post(self, request, pk):
        hydra = Hydra(spawn_id=pk)
        hydra.terminate()

        # Redirect back to monitor (refresh state)
        target_url = reverse('hydra:graph_monitor', kwargs={'spawn_id': pk})

        if request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = target_url
            return response

        return redirect(target_url)


# --- WAR ROOM ---


class HeadLogDetailView(DetailView):
    model = HydraHead
    template_name = 'hydra/head_detail.html'
    context_object_name = 'head'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        head = self.object

        # 1. Handle Log Stream Polling (Raw Text)
        if request.GET.get('partial') == 'content':
            log_type = request.GET.get('type', 'tool')
            content = ''

            if log_type == 'tool':
                content = head.spell_log or ''
            elif log_type == 'system':
                content = head.execution_log or ''

            # Return raw text so HTMX can append/replace cleanly
            return HttpResponse(content, content_type='text/plain')

        # 2. Handle Status Pill Polling (HTML Fragment)
        if request.GET.get('partial') == 'status_pill':
            html = f'''
            <div id="head-status-pill"
                 class="status-pill status-{head.status.name.lower()}"
                 hx-get="{request.path}?partial=status_pill"
                 hx-trigger="every 2s"
                 hx-swap="outerHTML">
                {head.status.name}
            </div>
            '''
            return HttpResponse(html)

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        head = self.object
        executable = head.spell.talos_executable

        # Set default log type for the main page load
        context['log_type'] = self.request.GET.get('type', 'tool')

        # Determine initial content for the template render
        if context['log_type'] == 'tool':
            context['initial_log_content'] = head.spell_log
        elif context['log_type'] == 'system':
            context['initial_log_content'] = head.execution_log

        # Logic for side-by-side file viewing (Legacy log file support)
        context['show_side_by_side'] = False
        if executable.log:
            log_path = executable.log
            if os.path.exists(log_path):
                context['show_side_by_side'] = True
                context['log_file_path'] = log_path
                try:
                    with open(
                        log_path, 'r', encoding='utf-8', errors='replace'
                    ) as f:
                        context['log_file_content'] = f.read()
                except Exception as e:
                    context['log_file_content'] = f'Error reading log file: {e}'

        return context


# --- LEGACY / UTILS ---


class HydraControlsView(TemplateView):
    template_name = 'hydra/controls.html'


class SpawnMonitorDetailView(DetailView):
    model = HydraSpawn
    template_name = 'hydra/spawn_monitor.html'
    context_object_name = 'spawn'
