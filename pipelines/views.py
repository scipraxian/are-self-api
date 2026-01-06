from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from pipelines.models import BuildProfile, PipelineRun, PipelineStepRun
from pipelines.tasks import orchestrate_pipeline
import re
import logging

logger = logging.getLogger(__name__)

def dashboard_campaign_section(request):
    """View to render the campaign section on the dashboard."""
    # Force Launcher: If user explicitly asks for it via ?force=true
    force = request.GET.get('force')
    
    active_run = PipelineRun.objects.filter(status='RUNNING').first()
    if active_run and not force:
        try:
            return pipeline_live_monitor(request, active_run.id)
        except Exception as e:
            logger.error(f"Active run corrupted: {e}")
            active_run.status = 'FAILED'
            active_run.save()

    profiles = list(BuildProfile.objects.all().order_by('name'))
    recent_runs = PipelineRun.objects.order_by('-created_at')[:5]
    
    return render(request, 'pipelines/partials/launch_campaign.html', {
        'profiles': profiles,
        'recent_runs': recent_runs
    })

@require_POST
def launch_pipeline(request):
    profile_id = request.POST.get('profile_id')
    profile = get_object_or_404(BuildProfile, id=profile_id)
    
    # 1. Create the Run
    run = PipelineRun.objects.create(profile=profile, status='PENDING')
    
    # 2. PRE-CREATE STEPS (Synchronous)
    # This guarantees the UI is never empty, even if Celery is slow.
    if profile.headless:
        PipelineStepRun.objects.create(pipeline_run=run, step_name="Headless Validator", status='PENDING', logs="Waiting for worker...")
    if profile.staging:
        PipelineStepRun.objects.create(pipeline_run=run, step_name="Staging Builder", status='PENDING', logs="Waiting for worker...")

    # 3. Launch Celery
    chain = orchestrate_pipeline(profile.id, run.id)
    if chain:
        result = chain.apply_async()
        run.celery_task_id = result.id
        run.status = 'RUNNING'
        run.save()
        return pipeline_live_monitor(request, run.id)
    else:
        run.status = 'FAILED'
        run.finished_at = timezone.now()
        run.save()
        return HttpResponse("Error: No tasks defined.")

def pipeline_live_monitor(request, run_id):
    run = get_object_or_404(PipelineRun, id=run_id)
    steps = run.steps.all().order_by('started_at')
    
    # Poll if Running OR if Pending (waiting for worker pick-up)
    is_active = (run.status in ['RUNNING', 'PENDING'])
    
    return render(request, 'pipelines/live_monitor.html', {
        'run': run,
        'steps': steps,
        'is_active': is_active
    })

def pipeline_live_logs_partial(request, step_id):
    step = get_object_or_404(PipelineStepRun, id=step_id)
    content = step.logs
    if not content:
        content = f"Waiting for logs... (Status: {step.status})"
    else:
        patterns = [
            (r'(Error:)', r'<span style="color:#f87171; font-weight:bold;">\1</span>'),
            (r'(Warning:)', r'<span style="color:#fbbf24; font-weight:bold;">\1</span>'),
            (r'(SUCCESS:)', r'<span style="color:#4ade80; font-weight:bold;">\1</span>'),
            (r'(=== EXECUTION CONTEXT ===)', r'<span style="color:#a78bfa; font-weight:bold; display:block; border-bottom: 1px solid #a78bfa; margin-bottom: 10px;">\1</span>'),
            (r'(Cmd:)', r'<span style="color:#22d3ee; font-weight:bold;">\1</span>'),
        ]
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)

    return HttpResponse(f"<pre style='margin: 0; white-space: pre-wrap; font-family: monospace;'>{content}</pre>")

@require_POST
def reset_campaign_view(request):
    PipelineRun.objects.filter(status='RUNNING').update(status='FAILED', finished_at=timezone.now())
    return dashboard_campaign_section(request)