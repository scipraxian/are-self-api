from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from pipelines.models import BuildProfile, PipelineRun, PipelineStepRun
from pipelines.tasks import orchestrate_pipeline

def dashboard_campaign_section(request):
    """View to render the campaign section on the dashboard."""
    active_run = PipelineRun.objects.filter(status='RUNNING').first()
    if active_run:
        return pipeline_live_monitor(request, active_run.id)
    
    profiles = BuildProfile.objects.all()
    return render(request, 'pipelines/partials/launch_campaign.html', {'profiles': profiles})

@require_POST
def launch_pipeline(request):
    """Handles the HTMX request to launch a pipeline."""
    profile_id = request.POST.get('profile_id')
    profile = BuildProfile.objects.get(id=profile_id)
    
    # Create the run record
    run = PipelineRun.objects.create(profile=profile, status='PENDING')
    
    # Orchestrate and start the chain with run ID
    chain = orchestrate_pipeline(profile.id, run.id)
    if chain:
        result = chain.apply_async()
        run.celery_task_id = result.id
        run.status = 'RUNNING'
        run.save()
        
        return HttpResponse(f"""
            <div id="campaign-launcher" hx-get="/pipelines/monitor/{run.id}/" hx-trigger="load" hx-swap="outerHTML">
                <!-- Redirecting to Monitor... -->
            </div>
        """)
    else:
        run.status = 'FAILED'
        run.finished_at = timezone.now()
        run.save()
        return HttpResponse("<p style='color: #ef4444;'>Error: No tasks in profile.</p>")

def pipeline_live_monitor(request, run_id):
    """Renders the live monitoring dashboard for a specific run."""
    run = get_object_or_404(PipelineRun, id=run_id)
    steps = run.steps.all().order_by('started_at')
    
    return render(request, 'pipelines/live_monitor.html', {
        'run': run,
        'steps': steps,
        'is_active': run.status == 'RUNNING'
    })

def pipeline_live_logs_partial(request, step_id):
    """HTMX partial to stream logs for a step."""
    step = get_object_or_404(PipelineStepRun, id=step_id)
    return HttpResponse(f"<pre style='color: #94a3b8; font-family: monospace; font-size: 0.85rem; line-height: 1.4; white-space: pre-wrap;'>{step.logs}</pre>")

@require_POST
def reset_campaign_view(request):
    """Force resets the campaign view by marking RUNNING runs as FAILED."""
    PipelineRun.objects.filter(status='RUNNING').update(status='FAILED', finished_at=timezone.now())
    return dashboard_campaign_section(request)
