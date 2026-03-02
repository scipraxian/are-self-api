import json

from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView

from central_nervous_system.central_nervous_system import CNS
from central_nervous_system.models import NeuralPathway, Spike, SpikeTrain
from central_nervous_system.utils import (
    get_active_environment,
    resolve_environment_context,
)
from ue_tools.merge_logs import merge_logs

# --- GRAPH VIEWS ---


class CNSGraphEditorView(DetailView):
    model = NeuralPathway
    template_name = 'central_nervous_system/graph_editor.html'
    context_object_name = 'book'
    pk_url_kwarg = 'pathway_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mode'] = 'edit'
        context['spike_train_id'] = ''
        return context


class CNSGraphMonitorView(DetailView):
    model = SpikeTrain
    template_name = 'central_nervous_system/graph_editor.html'
    context_object_name = 'spike_train'
    pk_url_kwarg = 'spike_train_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['book'] = self.object.pathway
        context['mode'] = 'monitor'
        context['spike_train_id'] = str(self.object.id)
        context['spike_train_history'] = SpikeTrain.objects.filter(
            pathway=self.object.pathway
        ).order_by('-created')[:20]
        return context


class LaunchNeuralPathwayView(View):
    """
    Launches the graph and forces a hard browser redirect.
    """

    def dispatch_launch(self, pathway_id):
        controller = CNS(pathway_id=pathway_id)
        controller.start()

        target_url = reverse(
            'central_nervous_system:graph_monitor', kwargs={'spike_train_id': controller.spike_train.id}
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

    def get(self, request, pathway_id):
        return self.dispatch_launch(pathway_id)

    def post(self, request, pathway_id):
        return self.dispatch_launch(pathway_id)


class ToggleFavoriteView(View):
    """
    Toggles the is_favorite status of a NeuralPathway.
    Returns the new Star Icon state HTML.
    """

    def post(self, request, pk):
        book = get_object_or_404(NeuralPathway, pk=pk)
        book.is_favorite = not book.is_favorite
        book.save(update_fields=['is_favorite'])

        # Return the updated SVG button
        return render(
            request, 'dashboard/partials/star_toggle.html', {'book': book}
        )


class TerminateSpawnView(View):
    """Aborts a running SpikeTrain (Nuclear Option)."""

    def post(self, request, pk):
        cns = CNS(spike_train_id=pk)
        cns.terminate()

        target_url = reverse('central_nervous_system:graph_monitor', kwargs={'spike_train_id': pk})

        if request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = target_url
            return response

        return redirect(target_url)


class GracefulStopSpawnView(View):
    """Asks the spikes to stop gracefully (Gentle Tap)."""

    def post(self, request, pk):
        cns = CNS(spike_train_id=pk)
        cns.stop_gracefully()

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

            # 1. WAR ROOM (Spike Detail) logic
            if '/spike/' in referer:
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

        target_url = reverse('central_nervous_system:graph_monitor', kwargs={'spike_train_id': pk})
        return redirect(target_url)


# --- WAR ROOM ---


class HeadLogDetailView(DetailView):
    model = Spike
    template_name = 'central_nervous_system/spike_detail.html'
    context_object_name = 'spike'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        spike = self.object
        is_active = spike.is_active
        log_type = request.GET.get('type')
        content = ''
        if log_type == 'tool':
            content = spike.application_log or ''
        elif log_type == 'system':
            content = spike.execution_log or ''
        if request.GET.get('format') == 'raw':
            return HttpResponse(content, content_type='text/plain')
        if request.GET.get('partial') == 'status_pill':
            trigger = 'hx-trigger="every 2s"' if is_active else ''
            html = f'''
            <div id="spike-status-pill"
                 class="status-pill status-{spike.status.name.lower()}"
                 hx-get="{request.path}?partial=status_pill"
                 {trigger}
                 hx-swap="outerHTML">
                {spike.status.name}
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
                    'central_nervous_system:cns_spawn_stop_graceful', args=[spike.spike_train.id]
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
        spike = self.object
        context['is_active'] = spike.is_active
        return context


# --- BATTLE STATION VIEWS ---


class CNSBattleStationView(DetailView):
    """
    Renders the Side-by-Side 'Battle Station' view for two selected spikes.
    """

    model = SpikeTrain
    template_name = 'central_nervous_system/spike_train_monitor_page.html'
    context_object_name = 'spike_train'
    pk_url_kwarg = 'spike_train_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_battle_mode'] = True
        context['is_active'] = self.object.is_active
        s1_id = self.request.GET.get('s1')
        s2_id = self.request.GET.get('s2')
        if s1_id and s2_id:
            try:
                context['spike_1'] = Spike.objects.get(id=s1_id)
                context['spike_2'] = Spike.objects.get(id=s2_id)
            except Spike.DoesNotExist:
                pass
        return context


class CNSBattleStreamView(View):
    """
    HTMX Endpoint: Merges logs from two spikes into a single time-indexed stream.
    Supports incremental updates via cursors.
    """

    def get(self, request, spike_train_id):
        try:
            spike_train = SpikeTrain.objects.get(id=spike_train_id)
        except SpikeTrain.DoesNotExist:
            return HttpResponse('SpikeTrain not found', status=404)

        s1_id = request.GET.get('s1')
        s2_id = request.GET.get('s2')

        # Cursor Handling
        try:
            cursor_1 = int(request.GET.get('local_cursor', 0))
            cursor_2 = int(request.GET.get('remote_cursor', 0))
        except (ValueError, TypeError):
            cursor_1 = 0
            cursor_2 = 0

        try:
            s1 = Spike.objects.get(id=s1_id)
            s2 = Spike.objects.get(id=s2_id)
        except Spike.DoesNotExist:
            return HttpResponse('Invalid Spike IDs', status=404)

        full_log1 = s1.application_log or s1.execution_log or ''
        full_log2 = s2.application_log or s2.execution_log or ''

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
            'central_nervous_system/partials/battle_stream.html',
            {
                'events': events,
                'new_local_cursor': new_cursor_1,
                'new_remote_cursor': new_cursor_2,
                'is_active': spike_train.is_active,
            },
        )


class CNSControlsView(TemplateView):
    template_name = 'central_nervous_system/controls.html'


class SpawnMonitorDetailView(DetailView):
    model = SpikeTrain
    template_name = 'central_nervous_system/spike_train_monitor.html'
    context_object_name = 'spike_train'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_full_page'] = self.request.GET.get('full') == 'True'
        context['is_active'] = self.object.is_active
        return context


def generate_spawn_dump(spike_train, depth=0):
    """Generator that streams the entire execution context of a SpikeTrain and its subgraphs."""
    indent = '    ' * depth

    yield f'{indent}TALOS SPAWN EXPORT {"(SUBGRAPH)" if depth > 0 else ""}\n'
    yield f'{indent}================================================================================\n'
    yield f'{indent}SpikeTrain ID:   {spike_train.id}\n'
    yield f'{indent}NeuralPathway:  {spike_train.pathway.name if spike_train.pathway else "Deleted"}\n'
    yield f'{indent}Status:     {spike_train.status.name}\n'
    yield f'{indent}Created:    {spike_train.created}\n'
    yield f'{indent}Environment: {spike_train.environment.name if spike_train.environment else "None"}\n'
    yield f'{indent}================================================================================\n\n'

    # Fetch all spikes in order
    spikes = (
        spike_train.spikes.all()
        .order_by('created')
        .select_related(
            'effector', 'status', 'target', 'neuron', 'spell__talos_executable'
        )
    )

    for i, spike in enumerate(spikes):
        yield f'{indent}--- HEAD #{i + 1} [{spike.id}] ---\n'
        yield f'{indent}Spell:      {spike.effector.name if spike.effector else "None"}\n'
        yield f'{indent}Status:     {spike.status.name}\n'
        yield f'{indent}Target:     {spike.target.hostname if spike.target else "Local Server"}\n'

        # Resolve the command string for context
        cmd_str = 'Command resolution failed'
        try:
            env = get_active_environment(spike)
            ctx = resolve_environment_context(spike_id=spike.id)
            if spike.effector:
                full_cmd = spike.effector.get_full_command(
                    environment=env, extra_context=ctx
                )
                cmd_str = ' '.join(full_cmd)
            else:
                cmd_str = '<No Effector Attached>'
        except Exception as e:
            cmd_str = f'<Error: {e}>'

        yield f'{indent}Command:    {cmd_str}\n'
        yield f'{indent}Result RC:  {spike.result_code}\n'

        # Output the exact Blackboard state!
        if spike.blackboard:
            yield f'{indent}Blackboard: {json.dumps(spike.blackboard)}\n'

        yield f'\n{indent}[SPELL LOG (Tool Output)]\n'
        yield f'{indent}-------------------------\n'
        if spike.application_log:
            yield spike.application_log
        else:
            yield f'<No Output>'
        yield f'\n'

        yield f'\n{indent}[EXECUTION LOG (System)]\n'
        yield f'{indent}------------------------\n'
        if spike.execution_log:
            yield spike.execution_log
        else:
            yield f'<No System Logs>'
        yield f'\n'
        yield f'\n'
        yield f'{indent}================================================================================\n\n'
        child_trains = spike.child_trains.all().order_by('created')
        for child in child_trains:
            yield from generate_spawn_dump(child, depth + 1)


class SpikeTrainDownloadView(View):
    """Streams all data from a spike_train into a single .log file download."""

    def get(self, request, pk):
        spike_train = get_object_or_404(SpikeTrain, pk=pk)

        response = StreamingHttpResponse(
            generate_spawn_dump(spike_train), content_type='text/plain'
        )

        filename = f'Spawn_{str(spike_train.id)[:8]}_{spike_train.status.name}.log'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
