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

        # --- NEW: History for Sidebar ---
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

        is_active = head.is_active
        if request.GET.get('partial') == 'content':
            log_type = request.GET.get('type', 'tool')
            content = ''
            if log_type == 'tool':
                content = head.spell_log or ''
            elif log_type == 'system':
                content = head.execution_log or ''
            elif log_type == 'file':
                if (
                    head.spell.talos_executable
                    and head.spell.talos_executable.log
                ):
                    log_path = head.spell.talos_executable.log
                    if os.path.exists(log_path):
                        try:
                            with open(
                                log_path,
                                'r',
                                encoding='utf-8',
                                errors='replace',
                            ) as f:
                                content = f.read()
                        except Exception as e:
                            content = f'[System Error reading file]: {e}'
                    else:
                        content = (
                            f'[Waiting for log file creation at: {log_path}...]'
                        )
                else:
                    content = '[No Log File configured for this Spell]'

            response = HttpResponse(content, content_type='text/plain')
            if is_active:
                response['HX-Trigger'] = 'every 1s'

            return response
        if request.GET.get('partial') == 'status_pill':
            trigger_attr = 'hx-trigger="every 2s"' if is_active else ''
            html = f'''
            <div id="head-status-pill"
                 class="status-pill status-{head.status.name.lower()}"
                 hx-get="{request.path}?partial=status_pill"
                 {trigger_attr}
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

        # Safe Executable Access
        executable = (
            head.spell.talos_executable if head.spell.talos_executable else None
        )

        # Determine initial content for the main render
        log_type = self.request.GET.get('type')
        if not log_type:
            log_type = (
                'system'
                if head.execution_log and not head.spell_log
                else 'tool'
            )

        context['log_type'] = log_type
        context['initial_log_content'] = (
            head.execution_log if log_type == 'system' else head.spell_log
        )

        # Check for side-by-side file capability
        context['show_side_by_side'] = False
        if executable and executable.log:
            log_path = executable.log
            context['log_file_path'] = log_path
            # We assume if a path is configured, we want to show the pane,
            # even if the file doesn't exist yet (it might be created during the run).
            context['show_side_by_side'] = True

            if os.path.exists(log_path):
                try:
                    with open(
                        log_path, 'r', encoding='utf-8', errors='replace'
                    ) as f:
                        context['log_file_content'] = f.read()
                except Exception as e:
                    context['log_file_content'] = f'Error reading log file: {e}'
            else:
                context['log_file_content'] = 'Waiting for log file...'

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

        # Get Head IDs from query params
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

        # Get Content (prefer spell_log, fallback to execution_log)
        log1 = h1.spell_log or h1.execution_log or ''
        log2 = h2.spell_log or h2.execution_log or ''

        # Merge logs
        events = merge_logs(log1, log2)

        return render(
            request,
            'hydra/partials/battle_stream.html',
            {
                'events': events,
                # Reset cursors for now, robust incremental sync requires client-side tracking logic update
                'new_local_cursor': len(log1),
                'new_remote_cursor': len(log2),
            },
        )


# --- LEGACY / UTILS ---


class HydraControlsView(TemplateView):
    template_name = 'hydra/controls.html'


class SpawnMonitorDetailView(DetailView):
    model = HydraSpawn
    template_name = 'hydra/spawn_monitor.html'
    context_object_name = 'spawn'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass 'full' param back to context to persist state during HTMX polling
        context['is_full_page'] = self.request.GET.get('full') == 'True'
        context['is_active'] = self.object.is_active
        return context


# END FILE
