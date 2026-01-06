from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from pipelines.models import BuildProfile, PipelineRun, PipelineStepRun
from pipelines.tasks import orchestrate_pipeline

def dashboard_campaign_section(request):
    """View to render the campaign section on the dashboard."""
    # 1. Check for Active Run (Redirect to Monitor if running)
    active_run = PipelineRun.objects.filter(status='RUNNING').first()
    if active_run:
        return pipeline_live_monitor(request, active_run.id)

    # 2. Fetch Data (Simple & Direct)
    profiles = BuildProfile.objects.all().order_by('name')
    recent_runs = PipelineRun.objects.order_by('-created_at')[:5]
    
    return render(request, 'pipelines/partials/launch_campaign.html', {
        'profiles': profiles,
        'recent_runs': recent_runs
    })

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
        
        return pipeline_live_monitor(request, run.id)
    else:
        run.status = 'FAILED'
        run.finished_at = timezone.now()
        run.save()
        return HttpResponse('''
            <div id="campaign-launcher">
                <p style="color: #ef4444; padding: 1rem; background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; border-radius: 12px;">
                    Error: No tasks defined for this profile.
                </p>
                <button hx-get="/pipelines/campaign-section/" hx-target="#campaign-launcher" hx-swap="outerHTML" style="margin-top: 1rem;" class="reset-button">Back</button>
            </div>
        ''')

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
    # Ensure we get the step or 404
    step = get_object_or_404(PipelineStepRun, id=step_id)
    
    # Default message if empty
    content = step.logs
    if not content:
        content = f"Waiting for logs... (Step Status: {step.status})"
        
    # We strip the style attribute here because the CSS class .log-content-box handles it
    return HttpResponse(f"<pre style='margin: 0; white-space: pre-wrap;'>{content}</pre>")

@require_POST
def reset_campaign_view(request):
    """Force resets the campaign view by marking RUNNING runs as FAILED."""
    PipelineRun.objects.filter(status='RUNNING').update(status='FAILED', finished_at=timezone.now())
    return dashboard_campaign_section(request)
