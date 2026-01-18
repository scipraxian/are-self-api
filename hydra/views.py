from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.urls import reverse
from django.views import View
from .models import HydraSpellbook, HydraEnvironment, HydraSpawn, HydraHead, HydraSpawnStatus
from .hydra import Hydra
from environments.models import ProjectEnvironment
import logging
from django.utils.html import escape
from talos_thalamus.types import SignalTypeID
from talos_thalamus.models import Stimulus
from talos_frontal.logic import process_stimulus

logger = logging.getLogger(__name__)


class LaunchSpellbookView(View):

    def post(self, request, spellbook_id):
        # 0. Check if any HydraSpawn is already active
        active_spawn = HydraSpawn.objects.filter(status_id__in=[
            HydraSpawnStatus.CREATED, HydraSpawnStatus.PENDING,
            HydraSpawnStatus.RUNNING
        ]).order_by('-created').first()

        if active_spawn:
            # Nudge it
            try:
                Hydra(spawn_id=active_spawn.id).poll()
                active_spawn.refresh_from_db()
            except Exception:
                pass

            if active_spawn.is_active:
                # If HTMX request, return the busy state UI
                if request.headers.get('HX-Request'):
                    return render(
                        request, 'dashboard/partials/hydra_button.html', {
                            'active_spawn':
                                active_spawn,
                            'spawn':
                                active_spawn,
                            'heads':
                                active_spawn.heads.all().order_by('spell__order'
                                                                 ),
                            'is_active':
                                active_spawn.is_active,
                            'spawn_history':
                                HydraSpawn.objects.all().order_by('-created')
                                [:5]
                        })
                # Otherwise just redirect to monitor
                return redirect('hydra_spawn_monitor', spawn_id=active_spawn.id)

        try:
            spellbook = HydraSpellbook.objects.get(id=spellbook_id)
        except HydraSpellbook.DoesNotExist:
            return render(
                request,
                'hydra/partials/error.html',
                {'message': f"Error: Spellbook {spellbook_id} not found."},
                status=404)

        env = ProjectEnvironment.objects.filter(is_active=True).first()
        if not env:
            return render(request,
                          'hydra/partials/error.html',
                          {'message': "No Active Environment."},
                          status=400)

        hydra_env, _ = HydraEnvironment.objects.get_or_create(
            project_environment=env,
            defaults={'name': f"Auto-Env for {env.name}"})

        try:
            controller = Hydra(spellbook_id=spellbook.id, env_id=hydra_env.id)
            controller.start()
        except Exception as e:
            logger.exception("[HYDRA] Launch Failed")
            return render(request,
                          'hydra/partials/error.html', {'message': str(e)},
                          status=500)

        # NEW: Trigger a page redirect to the monitor view, but for HTMX
        # we can also just swap the buttons to show the "Running" state if we wanted.
        # However, the user said "GUI to just be the current running item".
        # If we redirect to the monitor page, it fulfills that.

        if request.headers.get('HX-Request'):
            # Return the embedded monitor fragment
            spawn = controller.spawn
            return render(
                request, 'dashboard/partials/hydra_button.html', {
                    'active_spawn':
                        spawn,
                    'spawn':
                        spawn,
                    'heads':
                        spawn.heads.all().order_by('spell__order'),
                    'is_active':
                        spawn.is_active,
                    'spawn_history':
                        HydraSpawn.objects.all().order_by('-created')[:5]
                })

        return redirect('hydra_spawn_monitor', spawn_id=controller.spawn.id)


def spawn_monitor_view(request, spawn_id):
    spawn = get_object_or_404(HydraSpawn, id=spawn_id)

    # Nudge the state machine
    if spawn.is_active:
        controller = Hydra(spawn_id=spawn.id)
        controller.poll()
        spawn.refresh_from_db()

    heads = spawn.heads.all().order_by('spell__order')
    is_active = spawn.is_active
    is_full_page = request.GET.get('full') == 'True'

    # Check if this is a standalone request (needs full page) or HTMX poll (partial)
    if not request.headers.get('HX-Request'):
        return render(request, 'hydra/spawn_monitor_page.html', {
            'spawn': spawn,
            'heads': heads,
            'is_active': is_active
        })

    return render(
        request, 'hydra/spawn_monitor.html', {
            'spawn': spawn,
            'heads': heads,
            'is_active': is_active,
            'is_full_page': is_full_page
        })


def head_log_view(request, head_id):
    head = get_object_or_404(HydraHead, id=head_id)
    log_type = request.GET.get('type', 'tool')
    is_partial = request.GET.get('partial') == 'content'

    content = ""
    if log_type == 'system':
        content = head.execution_log or "No system events logged."
    elif log_type == 'stimulus':
        thought = head.thoughts.last()
        content = thought.used_prompt if thought else "No stimulus recorded for this head."
    else:
        content = head.spell_log or "Waiting for output..."

    if is_partial:
        # Return JUST the text content for the poller
        safe_content = escape(content)
        # Add headers for context
        if log_type == 'system':
            return HttpResponse(
                f'<div style="color: #60a5fa; margin-bottom: 10px;">--- SYSTEM DIAGNOSTICS ---</div>{safe_content}'
            )
        elif log_type == 'stimulus':
            return HttpResponse(
                f'<div style="color: #eab308; margin-bottom: 10px;">--- NEURAL STIMULUS (SYSTEM PROMPT) ---</div>{safe_content}'
            )

        return HttpResponse(safe_content)

    # Return FULL UI for initial tab load
    return render(request, 'hydra/partials/head_log.html', {
        'head': head,
        'content': content,
        'log_type': log_type
    })


def hydra_head_analysis(request, head_id):
    head = get_object_or_404(HydraHead, id=head_id)
    thought = head.thoughts.last()

    return render(request, 'hydra/partials/head_analysis.html',
                  {'thought': thought})


class HydraControlsView(View):

    def get(self, request):
        active_spawn = HydraSpawn.objects.filter(status_id__in=[
            HydraSpawnStatus.CREATED, HydraSpawnStatus.PENDING,
            HydraSpawnStatus.RUNNING
        ]).order_by('-created').first()

        if active_spawn:
            # Nudge it
            try:
                Hydra(spawn_id=active_spawn.id).poll()
                active_spawn.refresh_from_db()
            except Exception:
                pass

        # Check again after nudge
        if active_spawn and not active_spawn.is_active:
            active_spawn = None

        spellbooks = HydraSpellbook.objects.all().order_by('name')

        context = {
            'active_spawn': active_spawn,
            'hydra_spellbooks': spellbooks,
            'spawn_history': HydraSpawn.objects.all().order_by('-created')[:5]
        }
        if active_spawn:
            context.update({
                'spawn': active_spawn,
                'heads': active_spawn.heads.all().order_by('spell__order'),
                'is_active': True
            })

        return render(request, 'dashboard/partials/hydra_button.html', context)


def hydra_spawn_terminate(request, spawn_id):
    spawn = get_object_or_404(HydraSpawn, id=spawn_id)
    action = request.GET.get('action')

    controller = Hydra(spawn_id=spawn.id)
    controller.terminate()

    # ONLY Trigger AI if explicitly requested
    if action == 'analyze':
        stimulus = Stimulus(
            source='hydra',
            description=f"Multiplayer Debug Session {spawn.id} Finalized",
            context_data={
                'spawn_id': str(spawn.id),
                'event_type': SignalTypeID.MULTIPLAYER_DEBUG
            })
        process_stimulus(stimulus)
        return HttpResponse("Session terminated. Analysis started.")

    # Default: Just stop
    return HttpResponse("Session terminated. No analysis triggered.")
