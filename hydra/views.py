import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.views import View

from .hydra import Hydra
from .models import (
    HydraHead,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpellbook,
)
from .utils import merge_logs

logger = logging.getLogger(__name__)


class LaunchSpellbookView(View):
    def post(self, request, spellbook_id):
        # 0. Check if any HydraSpawn is already active
        active_spawn = (
            HydraSpawn.objects.filter(
                status_id__in=[
                    HydraSpawnStatus.CREATED,
                    HydraSpawnStatus.PENDING,
                    HydraSpawnStatus.RUNNING,
                ]
            )
            .order_by('-created')
            .first()
        )

        if active_spawn:
            # Nudge it
            try:
                Hydra(spawn_id=active_spawn.id).poll()
                active_spawn.refresh_from_db()
            except Exception:
                pass

            if active_spawn.is_active:
                if request.headers.get('HX-Request'):
                    return render(
                        request,
                        'dashboard/partials/hydra_button.html',
                        {
                            'active_spawn': active_spawn,
                            'spawn': active_spawn,
                            'heads': active_spawn.heads.all().order_by(
                                'spell__order'
                            ),
                            'is_active': active_spawn.is_active,
                            'spawn_history': HydraSpawn.objects.all().order_by(
                                '-created'
                            )[:5],
                        },
                    )
                return redirect('hydra_spawn_monitor', spawn_id=active_spawn.id)

        try:
            spellbook = HydraSpellbook.objects.get(id=spellbook_id)
        except HydraSpellbook.DoesNotExist:
            return render(
                request,
                'hydra/partials/error.html',
                {'message': f'Error: Spellbook {spellbook_id} not found.'},
                status=404,
            )

        # env = ProjectEnvironment.objects.filter(is_active=True).first()
        # if not env:
        #     return render(
        #         request,
        #         'hydra/partials/error.html',
        #         {'message': 'No Active Environment.'},
        #         status=400,
        #     )

        try:
            controller = Hydra(spellbook_id=spellbook.id)
            controller.start()
        except Exception as e:
            logger.exception('[HYDRA] Launch Failed')
            return render(
                request,
                'hydra/partials/error.html',
                {'message': str(e)},
                status=500,
            )

        if request.headers.get('HX-Request'):
            spawn = controller.spawn
            return render(
                request,
                'dashboard/partials/hydra_button.html',
                {
                    'active_spawn': spawn,
                    'spawn': spawn,
                    'heads': spawn.heads.all().order_by('spell__order'),
                    'is_active': spawn.is_active,
                    'spawn_history': HydraSpawn.objects.all().order_by(
                        '-created'
                    )[:5],
                },
            )

        return redirect('hydra_spawn_monitor', spawn_id=controller.spawn.id)


def spawn_monitor_view(request, spawn_id):
    spawn = get_object_or_404(HydraSpawn, id=spawn_id)

    if spawn.is_active:
        controller = Hydra(spawn_id=spawn.id)
        controller.poll()
        spawn.refresh_from_db()

    heads = spawn.heads.all().order_by('spell__order')
    is_active = spawn.is_active
    is_full_page = request.GET.get('full') == 'True'

    if not request.headers.get('HX-Request'):
        return render(
            request,
            'hydra/spawn_monitor_page.html',
            {'spawn': spawn, 'heads': heads, 'is_active': is_active},
        )

    return render(
        request,
        'hydra/spawn_monitor.html',
        {
            'spawn': spawn,
            'heads': heads,
            'is_active': is_active,
            'is_full_page': is_full_page,
        },
    )


def head_log_view(request, head_id):
    head = get_object_or_404(HydraHead, id=head_id)
    log_type = request.GET.get('type', 'tool')
    is_partial = request.GET.get('partial') == 'content'

    content = ''
    if log_type == 'system':
        content = head.execution_log or 'No system events logged.'
    elif log_type == 'stimulus':
        thought = head.thoughts.last()
        content = (
            thought.used_prompt
            if thought
            else 'No stimulus recorded for this head.'
        )
    else:
        content = head.spell_log or 'Waiting for output...'

    if is_partial:
        safe_content = escape(content)
        if log_type == 'system':
            return HttpResponse(
                f'<div style="color: #60a5fa; margin-bottom: 10px;">--- SYSTEM DIAGNOSTICS ---</div>{safe_content}'
            )
        elif log_type == 'stimulus':
            return HttpResponse(
                f'<div style="color: #eab308; margin-bottom: 10px;">--- NEURAL STIMULUS (SYSTEM PROMPT) ---</div>{safe_content}'
            )
        return HttpResponse(safe_content)

    return render(
        request,
        'hydra/partials/head_log.html',
        {'head': head, 'content': content, 'log_type': log_type},
    )


def hydra_head_analysis(request, head_id):
    head = get_object_or_404(HydraHead, id=head_id)
    thought = head.thoughts.last()
    return render(
        request, 'hydra/partials/head_analysis.html', {'thought': thought}
    )


class HydraControlsView(View):
    def get(self, request):
        active_spawn = (
            HydraSpawn.objects.filter(
                status_id__in=[
                    HydraSpawnStatus.CREATED,
                    HydraSpawnStatus.PENDING,
                    HydraSpawnStatus.RUNNING,
                ]
            )
            .order_by('-created')
            .first()
        )

        if active_spawn:
            try:
                Hydra(spawn_id=active_spawn.id).poll()
                active_spawn.refresh_from_db()
            except Exception:
                pass

        if active_spawn and not active_spawn.is_active:
            active_spawn = None

        spellbooks = HydraSpellbook.objects.all().order_by('name')

        context = {
            'active_spawn': active_spawn,
            'hydra_spellbooks': spellbooks,
            'spawn_history': HydraSpawn.objects.all().order_by('-created')[:5],
        }
        if active_spawn:
            context.update(
                {
                    'spawn': active_spawn,
                    'heads': active_spawn.heads.all().order_by('spell__order'),
                    'is_active': True,
                }
            )

        return render(request, 'dashboard/partials/hydra_button.html', context)


def hydra_spawn_terminate(request, spawn_id):
    spawn = get_object_or_404(HydraSpawn, id=spawn_id)
    action = request.GET.get('action')

    controller = Hydra(spawn_id=spawn.id)
    controller.terminate()

    # if action == 'analyze':
    #     stimulus = Stimulus(
    #         source='hydra',
    #         description=f"Multiplayer Debug Session {spawn.id} Finalized",
    #         context_data={
    #             'spawn_id': str(spawn.id),
    #             'event_type': SignalTypeID.MULTIPLAYER_DEBUG
    #         })
    #     process_stimulus(stimulus)
    #     return HttpResponse("Session terminated. Analysis started.")

    return HttpResponse('Session terminated. No analysis triggered.')


def battle_station_stream(request, spawn_id):
    """
    Polled by the Battle Station to get new log lines.
    Uses cursors to only fetch and merge delta content.
    """
    spawn = get_object_or_404(HydraSpawn, id=spawn_id)

    # 1. Parse Cursors safely
    def get_cursor(key):
        try:
            val = request.GET.get(key)
            return int(val) if val and val != 'undefined' else 0
        except (ValueError, TypeError):
            return 0

    local_cursor = get_cursor('local_cursor')
    remote_cursor = get_cursor('remote_cursor')

    # 2. Identify Heads
    heads = spawn.heads.all()
    # Assuming standard spell names for now
    local_head = heads.filter(spell__name__icontains='Local').first()
    remote_head = heads.filter(spell__name__icontains='Remote').first()

    if not local_head or not remote_head:
        return HttpResponse(
            '<div style="color: #f87171; padding: 10px;">Error: Heads not found. Ensure spell names contain "Local" and "Remote".</div>'
        )

    # 3. Fetch Data (Optimized Slice)
    # Django might fetch full field then slice in python, but for medium logs this is acceptable.
    # Ideally we'd use Substr() in DB, but let's stick to Python for stability first.
    local_full = local_head.spell_log or ''
    remote_full = remote_head.spell_log or ''

    new_local = local_full[local_cursor:]
    new_remote = remote_full[remote_cursor:]

    # 4. Short-circuit if no new data
    if not new_local and not new_remote:
        return HttpResponse('')  # 204/Empty to save rendering

    # 5. Merge Strategy (The Integration)
    # This calls the updated utils.merge_logs which uses ue_tools
    merged_events = merge_logs(new_local, new_remote)

    # 6. Calculate New Cursors
    next_local_cursor = local_cursor + len(new_local)
    next_remote_cursor = remote_cursor + len(new_remote)

    return render(
        request,
        'hydra/partials/battle_stream.html',
        {
            'events': merged_events,
            'new_local_cursor': next_local_cursor,
            'new_remote_cursor': next_remote_cursor,
            'spawn': spawn,
        },
    )
