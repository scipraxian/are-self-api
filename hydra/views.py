import os

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView

from ue_tools.merge_logs import merge_logs

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
        context['spawn_history'] = HydraSpawn.objects.filter(
            spellbook=self.object.spellbook
        ).order_by('-created')[:20]
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

        if self.request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = target_url
            return response

        return redirect(target_url)

    def get(self, request, spellbook_id):
        return self.dispatch_launch(spellbook_id)

    def post(self, request, spellbook_id):
        return self.dispatch_launch(spellbook_id)


class TerminateSpawnView(View):
    """Aborts a running Spawn (Nuclear Option)."""

    def post(self, request, pk):
        hydra = Hydra(spawn_id=pk)
        hydra.terminate()

        target_url = reverse('hydra:graph_monitor', kwargs={'spawn_id': pk})

        if request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = target_url
            return response

        return redirect(target_url)


class GracefulStopSpawnView(View):
    """Asks the heads to stop gracefully (Gentle Tap)."""

    def post(self, request, pk):
        hydra = Hydra(spawn_id=pk)
        hydra.stop_gracefully()

        # FIX: The button must POLL to see if the stop completed.
        # We target the 'actions-container' which we will add to the templates.
        if request.headers.get('HX-Request'):
            referer = request.META.get('HTTP_REFERER', '')

            # Context-Aware Styling with Self-Polling
            # hx-select="#actions-container" pulls just the buttons from the current page
            # hx-target="#actions-container" replaces the buttons on the current page

            common_attrs = f'hx-get="{referer}" hx-select="#actions-container" hx-target="#actions-container" hx-swap="outerHTML" hx-trigger="every 1s"'

            if '/head/' in referer:
                # War Room Style
                return HttpResponse(
                    f'<div id="actions-container" class="war-actions" {common_attrs}>'
                    '<button class="btn-terminate" disabled style="opacity: 0.5; cursor: wait;">Stopping...</button>'
                    '</div>'
                )
            else:
                # Spawn Monitor Style
                return HttpResponse(
                    f'<div class="actions" {common_attrs}>'
                    '<button class="btn-done" disabled style="border-color: #fb923c; color: #fb923c; opacity: 0.8; cursor: wait;">Stopping...</button>'
                    '</div>'
                )

        # Fallback for non-JS requests
        target_url = reverse('hydra:graph_monitor', kwargs={'spawn_id': pk})
        return redirect(target_url)


# --- WAR ROOM ---


class HeadLogDetailView(DetailView):
    model = HydraHead
    template_name = 'hydra/head_detail.html'
    context_object_name = 'head'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        head = self.object
        is_active = head.is_active

        # HTMX Content Endpoint
        if request.GET.get('partial') == 'content':
            log_type = request.GET.get('type')
            content = ''

            if log_type == 'tool':
                content = head.spell_log or ''
            elif log_type == 'system':
                content = head.execution_log or ''

            # Simple Text Response. The Template JS will handle the terminal write.
            # We wrap it in a hidden div so HTMX can swap it into the DOM for JS to read.
            trigger = 'hx-trigger="every 1s"' if is_active else ''

            html = f'''
            <div id="buffer-{log_type}" 
                 class="raw-buffer"
                 hx-get="{request.path}?partial=content&type={log_type}"
                 hx-swap="outerHTML"
                 {trigger}
                 style="display: none;">{content}</div>
            '''
            return HttpResponse(html)

        # Status Pill Endpoint
        if request.GET.get('partial') == 'status_pill':
            trigger = 'hx-trigger="every 2s"' if is_active else ''
            html = f'''
            <div id="head-status-pill"
                 class="status-pill status-{head.status.name.lower()}"
                 hx-get="{request.path}?partial=status_pill"
                 {trigger}
                 hx-swap="outerHTML">
                {head.status.name}
            </div>
            '''
            return HttpResponse(html)

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        head = self.object
        context['is_active'] = head.is_active

        # Pre-load initial content for both panes
        context['initial_tool_log'] = head.spell_log or ''
        context['initial_system_log'] = head.execution_log or ''

        return context


# --- BATTLE STATION VIEWS ---


class HydraBattleStationView(DetailView):
    """
    Renders the Side-by-Side 'Battle Station' view for two selected heads.
    """

    model = HydraSpawn
    template_name = 'hydra/spawn_monitor_page.html'
    context_object_name = 'spawn'
    pk_url_kwarg = 'spawn_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_battle_mode'] = True
        context['is_active'] = self.object.is_active
        h1_id = self.request.GET.get('h1')
        h2_id = self.request.GET.get('h2')
        if h1_id and h2_id:
            try:
                context['head_1'] = HydraHead.objects.get(id=h1_id)
                context['head_2'] = HydraHead.objects.get(id=h2_id)
            except HydraHead.DoesNotExist:
                pass
        return context


class HydraBattleStreamView(View):
    """
    HTMX Endpoint: Merges logs from two heads into a single time-indexed stream.
    """

    def get(self, request, spawn_id):
        h1_id = request.GET.get('h1')
        h2_id = request.GET.get('h2')
        try:
            h1 = HydraHead.objects.get(id=h1_id)
            h2 = HydraHead.objects.get(id=h2_id)
        except HydraHead.DoesNotExist:
            return HttpResponse('Invalid Head IDs', status=404)

        log1 = h1.spell_log or h1.execution_log or ''
        log2 = h2.spell_log or h2.execution_log or ''
        events = merge_logs(log1, log2)

        return render(
            request,
            'hydra/partials/battle_stream.html',
            {
                'events': events,
                'new_local_cursor': len(log1),
                'new_remote_cursor': len(log2),
            },
        )


class HydraControlsView(TemplateView):
    template_name = 'hydra/controls.html'


class SpawnMonitorDetailView(DetailView):
    model = HydraSpawn
    template_name = 'hydra/spawn_monitor.html'
    context_object_name = 'spawn'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_full_page'] = self.request.GET.get('full') == 'True'
        context['is_active'] = self.object.is_active
        return context
