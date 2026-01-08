from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.views import View
from .models import HydraSpellbook, HydraEnvironment, HydraSpawn, HydraHead
from .hydra import Hydra
from environments.models import ProjectEnvironment
import logging
from django.utils.html import escape

logger = logging.getLogger(__name__)

class LaunchSpellbookView(View):
    def post(self, request, spellbook_id):
        try:
            spellbook = HydraSpellbook.objects.get(id=spellbook_id)
        except HydraSpellbook.DoesNotExist:
            return render(request, 'hydra/partials/error.html', {
                'message': f"Error: Spellbook {spellbook_id} not found."
            }, status=404)

        env = ProjectEnvironment.objects.filter(is_active=True).first()
        if not env:
            return render(request, 'hydra/partials/error.html', {'message': "No Active Environment."}, status=400)

        hydra_env, _ = HydraEnvironment.objects.get_or_create(
            project_environment=env,
            defaults={'name': f"Auto-Env for {env.name}"}
        )

        try:
            controller = Hydra(spellbook_id=spellbook.id, env_id=hydra_env.id)
            controller.start()
        except Exception as e:
            logger.exception("[HYDRA] Launch Failed")
            return render(request, 'hydra/partials/error.html', {'message': str(e)}, status=500)

        return spawn_monitor_view(request, controller.spawn.id)

def spawn_monitor_view(request, spawn_id):
    spawn = get_object_or_404(HydraSpawn, id=spawn_id)
    heads = spawn.heads.all().order_by('spell__order')
    is_active = spawn.status.name in ['Created', 'Pending', 'Running']
    
    # Check if this is a standalone request (needs full page) or HTMX poll (partial)
    if not request.headers.get('HX-Request'):
        return render(request, 'hydra/spawn_monitor_page.html', {
            'spawn': spawn, 'heads': heads, 'is_active': is_active
        })

    return render(request, 'hydra/spawn_monitor.html', {
        'spawn': spawn, 'heads': heads, 'is_active': is_active
    })

def head_log_view(request, head_id):
    head = get_object_or_404(HydraHead, id=head_id)
    log_type = request.GET.get('type', 'tool')
    is_partial = request.GET.get('partial') == 'content'
    
    content = ""
    if log_type == 'system':
        content = head.execution_log or "No system events logged."
    else:
        content = head.spell_log or "Waiting for output..."

    if is_partial:
        # Return JUST the text content for the poller
        safe_content = escape(content)
        if log_type == 'system':
            return HttpResponse(f'<div style="color: #60a5fa; margin-bottom: 10px;">--- SYSTEM DIAGNOSTICS ---</div>{safe_content}')
        return HttpResponse(safe_content)

    # Return FULL UI for initial tab load
    return render(request, 'hydra/partials/head_log.html', {
        'head': head,
        'content': content,
        'log_type': log_type
    })