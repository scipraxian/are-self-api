import os

from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView

from hydra.utils import get_active_environment, resolve_environment_context
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

        # Check for suppression flag in query params
        no_redirect = self.request.GET.get('no_redirect') == 'true'

        if self.request.headers.get('HX-Request'):
            if no_redirect:
                # Return 204 No Content so HTMX does nothing (Dashboard poll will pick it up)
                response = HttpResponse(status=204)
                # CRITICAL: Trigger the monitor to wake up and refresh
                response['HX-Trigger'] = 'monitor-update'
                return response

            response = HttpResponse()
            response['HX-Redirect'] = target_url
            return response

        return redirect(target_url)

    def get(self, request, spellbook_id):
        return self.dispatch_launch(spellbook_id)

    def post(self, request, spellbook_id):
        return self.dispatch_launch(spellbook_id)


class ToggleFavoriteView(View):
    """
    Toggles the is_favorite status of a Spellbook.
    Returns the new Star Icon state HTML.
    """

    def post(self, request, pk):
        book = get_object_or_404(HydraSpellbook, pk=pk)
        book.is_favorite = not book.is_favorite
        book.save(update_fields=['is_favorite'])

        # Return the updated SVG button
        return render(
            request, 'dashboard/partials/star_toggle.html', {'book': book}
        )


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

        if request.GET.get('silent') == 'true':
            return HttpResponse(status=204)

        # Context-Aware Response
        if request.headers.get('HX-Request'):
            referer = request.META.get('HTTP_REFERER', '')

            # Common stopping state button
            stopping_btn = (
                '<button class="btn-control stop" disabled '
                'style="opacity: 0.5; cursor: wait; border-color: #f97316; color: #f97316;">'
                '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
                '<rect x="6" y="6" width="12" height="12" rx="2" ry="2"></rect></svg>'
                '</button>'
            )

            # 1. WAR ROOM (Head Detail) logic
            if '/head/' in referer:
                # We use ?partial=actions to poll just the button, not the whole page
                return HttpResponse(
                    f'<div id="actions-container" style="display: inline-block;" '
                    f'hx-get="{referer}" hx-vals=\'{{"partial": "actions"}}\' '
                    f'hx-trigger="every 2s" hx-swap="outerHTML">'
                    f'<button class="btn-secondary" disabled style="opacity:0.5;">Stopping...</button>'
                    '</div>'
                )

            # 2. MONITOR / DASHBOARD logic
            else:
                # FIX: Do NOT try to poll .actions on dashboard as it doesn't exist in the partial.
                # Just return the disabled button. The main swimlane poll will pick up the 'Stopping' state naturally.
                return HttpResponse(stopping_btn)

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
        log_type = request.GET.get('type')
        content = ''
        if log_type == 'tool':
            content = head.spell_log or ''
        elif log_type == 'system':
            content = head.execution_log or ''
        if request.GET.get('format') == 'raw':
            return HttpResponse(content, content_type='text/plain')
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

        # 3. Actions Endpoint (HTMX Polling)
        # This is what the GracefulStopSpawnView polls to see if it should remove the button
        if request.GET.get('partial') == 'actions':
            trigger = 'hx-trigger="every 2s"' if is_active else ''

            button_html = ''
            # ONLY render the button if active. If not active, this returns empty string, removing it.
            if is_active:
                stop_url = reverse(
                    'hydra:hydra_spawn_stop_graceful', args=[head.spawn.id]
                )
                button_html = f'''
                <button class="btn-secondary" 
                        hx-post="{stop_url}"
                        hx-swap="outerHTML"
                        style="border-color: #f85149; color: #f85149; background: rgba(248, 81, 73, 0.1);">
                    Stop Process
                </button>
                '''

            html = f'''
            <div id="actions-container" style="display: inline-block;"
                 hx-get="{request.path}" hx-vals='{{"partial": "actions"}}'
                 {trigger}
                 hx-swap="outerHTML">
                {button_html}
            </div>
            '''
            return HttpResponse(html)

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        head = self.object
        context['is_active'] = head.is_active
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
    Supports incremental updates via cursors.
    """

    def get(self, request, spawn_id):
        try:
            spawn = HydraSpawn.objects.get(id=spawn_id)
        except HydraSpawn.DoesNotExist:
            return HttpResponse('Spawn not found', status=404)

        h1_id = request.GET.get('h1')
        h2_id = request.GET.get('h2')

        # Cursor Handling
        try:
            cursor_1 = int(request.GET.get('local_cursor', 0))
            cursor_2 = int(request.GET.get('remote_cursor', 0))
        except (ValueError, TypeError):
            cursor_1 = 0
            cursor_2 = 0

        try:
            h1 = HydraHead.objects.get(id=h1_id)
            h2 = HydraHead.objects.get(id=h2_id)
        except HydraHead.DoesNotExist:
            return HttpResponse('Invalid Head IDs', status=404)

        full_log1 = h1.spell_log or h1.execution_log or ''
        full_log2 = h2.spell_log or h2.execution_log or ''

        # Calculate Deltas
        delta_log1 = full_log1[cursor_1:]
        delta_log2 = full_log2[cursor_2:]

        # Only merge if there is content to merge
        # IMPORTANT: Return cursor/active update even if empty, so client knows to stop
        events = []
        if delta_log1 or delta_log2:
            events = merge_logs(delta_log1, delta_log2)

        new_cursor_1 = len(full_log1)
        new_cursor_2 = len(full_log2)

        return render(
            request,
            'hydra/partials/battle_stream.html',
            {
                'events': events,
                'new_local_cursor': new_cursor_1,
                'new_remote_cursor': new_cursor_2,
                'is_active': spawn.is_active,
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


def generate_spawn_dump(spawn):
    """Generator that streams the entire execution context of a Spawn."""
    yield f'TALOS SPAWN EXPORT\n'
    yield f'================================================================================\n'
    yield f'Spawn ID:   {spawn.id}\n'
    yield f'Spellbook:  {spawn.spellbook.name if spawn.spellbook else "Deleted"}\n'
    yield f'Status:     {spawn.status.name}\n'
    yield f'Created:    {spawn.created}\n'
    yield f'Environment: {spawn.environment.name if spawn.environment else "None"}\n'
    yield f'================================================================================\n\n'

    # Fetch all heads in order
    heads = (
        spawn.heads.all()
        .order_by('created')
        .select_related(
            'spell', 'status', 'target', 'node', 'spell__talos_executable'
        )
    )

    for i, head in enumerate(heads):
        yield f'--- HEAD #{i + 1} [{head.id}] ---\n'
        yield f'Spell:      {head.spell.name if head.spell else "None"}\n'
        yield f'Status:     {head.status.name}\n'
        yield f'Target:     {head.target.hostname if head.target else "Local Server"}\n'

        # Resolve the command string for context
        cmd_str = 'Command resolution failed'
        try:
            env = get_active_environment(head)
            ctx = resolve_environment_context(head_id=head.id)
            if head.spell:
                full_cmd = head.spell.get_full_command(
                    environment=env, extra_context=ctx
                )
                cmd_str = ' '.join(full_cmd)
            else:
                cmd_str = '<No Spell Attached>'
        except Exception as e:
            cmd_str = f'<Error: {e}>'

        yield f'Command:    {cmd_str}\n'
        yield f'Result RC:  {head.result_code}\n'

        yield f'\n[SPELL LOG (Tool Output)]\n'
        yield f'-------------------------\n'
        yield head.spell_log or '<No Output>'
        yield f'\n'

        yield f'\n[EXECUTION LOG (System)]\n'
        yield f'------------------------\n'
        yield head.execution_log or '<No System Logs>'
        yield f'\n'

        yield f'\n[Blackboard]\n'
        yield f'------------------------\n'
        yield str(head.blackboard) if head.blackboard else '<No Blackboard>'
        yield f'\n'
        yield f'================================================================================\n\n'


class HydraSpawnDownloadView(View):
    """Streams all data from a spawn into a single .log file download."""

    def get(self, request, pk):
        spawn = get_object_or_404(HydraSpawn, pk=pk)

        response = StreamingHttpResponse(
            generate_spawn_dump(spawn), content_type='text/plain'
        )

        filename = f'Spawn_{str(spawn.id)[:8]}_{spawn.status.name}.log'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
