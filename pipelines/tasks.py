import os
import subprocess
import logging
from celery import shared_task, chain
from django.utils import timezone
from environments.models import ProjectEnvironment
from pipelines.models import BuildProfile, PipelineRun, PipelineStepRun

logger = logging.getLogger(__name__)

def get_active_env():
    try:
        return ProjectEnvironment.objects.get(is_active=True)
    except ProjectEnvironment.DoesNotExist:
        logger.error("No active ProjectEnvironment found.")
        return None

@shared_task
def run_headless_tests_task(pipeline_run_id=None):
    run = None
    step = None
    if pipeline_run_id:
        run = PipelineRun.objects.get(id=pipeline_run_id)
        step = PipelineStepRun.objects.create(
            pipeline_run=run,
            step_name="Headless Validator",
            status='RUNNING'
        )

    env = get_active_env()
    if not env:
        msg = "FAILED: No active environment"
        if step:
            step.status = 'FAILED'
            step.logs = msg
            step.finished_at = timezone.now()
            step.save()
        return msg

    uproject_path = os.path.join(env.project_root, f"{env.project_name}.uproject")
    build_bat = os.path.join(env.engine_root, 'Engine', 'Build', 'BatchFiles', 'Build.bat')
    editor_cmd = os.path.join(env.engine_root, 'Engine', 'Binaries', 'Win64', 'UnrealEditor-Cmd.exe')
    log_dir = os.path.join(env.project_root, 'Saved', 'Logs', 'HeadlessTests')

    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logs = []
    def log_and_append(msg):
        logger.info(msg)
        logs.append(msg)
        if step:
            step.logs = "\n".join(logs)
            step.save()

    # 1. Compile Editor
    compile_args = [
        build_bat,
        f"{env.project_name}Editor",
        'Win64',
        'Development',
        f"-Project={uproject_path}",
        '-WaitMutex',
    ]
    log_and_append(f"Compiling Editor: {' '.join(compile_args)}")
    res = subprocess.run(compile_args, capture_output=True, text=True, shell=True)
    log_and_append(res.stdout)
    if res.returncode != 0:
        log_and_append(f"Compilation Failed with code {res.returncode}")
        if step:
            step.status = 'FAILED'
            step.finished_at = timezone.now()
            step.save()
        return "FAILED: Compilation Failed"

    # 2. Run Tests
    test_args = [
        editor_cmd,
        uproject_path,
        '-log',
        '-nullrhi',
        '-unattended',
        '-nopause',
        '-CustomConfig=Staging',
        f'-ReportExportPath={log_dir}',
        '-ExecCmds=Automation RunTests HSH.Tests; Quit',
        '-TestExit=Automation Test Queue Empty',
    ]
    log_and_append(f"Running Headless Tests: {' '.join(test_args)}")
    result = subprocess.run(test_args, capture_output=True, text=True)
    log_and_append(result.stdout)

    if result.returncode != 0:
        if step:
            step.status = 'FAILED'
            step.finished_at = timezone.now()
            step.save()
        return f"FAILED: Unit Tests Failed with code {result.returncode}"
    
    if step:
        step.status = 'SUCCESS'
        step.finished_at = timezone.now()
        step.save()
    return "SUCCESS: Headless Tests Passed"

@shared_task
def run_staging_build_task(pipeline_run_id=None):
    run = None
    step = None
    if pipeline_run_id:
        run = PipelineRun.objects.get(id=pipeline_run_id)
        step = PipelineStepRun.objects.create(
            pipeline_run=run,
            step_name="Staging Builder",
            status='RUNNING'
        )

    env = get_active_env()
    if not env:
        msg = "FAILED: No active environment"
        if step:
            step.status = 'FAILED'
            step.logs = msg
            step.finished_at = timezone.now()
            step.save()
        return msg

    uproject_path = os.path.join(env.project_root, f"{env.project_name}.uproject")
    uat_batch = os.path.join(env.engine_root, 'Engine', 'Build', 'BatchFiles', 'RunUAT.bat')
    staging_dir = env.staging_dir or os.path.join(env.build_root, 'Staging')

    logs = []
    def log_and_append(msg):
        logger.info(msg)
        logs.append(msg)
        if step:
            step.logs = "\n".join(logs)
            step.save()

    cmd = [
        uat_batch,
        'BuildCookRun',
        f'-project={uproject_path}',
        '-platform=Win64',
        '-clientconfig=Development',
        '-serverconfig=Development',
        '-build',
        '-cook',
        '-stage',
        '-pak',
        f'-stagingdirectory={staging_dir}',
        '-nocompileeditor',
        '-unattended',
        '-nopause',
        '-utf8output'
    ]
    
    log_and_append(f"Running Staging Build: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    log_and_append(result.stdout)

    if result.returncode != 0:
        if step:
            step.status = 'FAILED'
            step.finished_at = timezone.now()
            step.save()
        return f"FAILED: Staging Build Failed with code {result.returncode}"
    
    if step:
        step.status = 'SUCCESS'
        step.finished_at = timezone.now()
        step.save()
    return "SUCCESS: Staging Build Complete"

@shared_task
def finalize_pipeline_run(pipeline_run_id):
    logger.info(f"Finalizing PipelineRun {pipeline_run_id}")
    try:
        run = PipelineRun.objects.get(id=pipeline_run_id)
        all_success = all(s.status == 'SUCCESS' for s in run.steps.all())
        run.status = 'SUCCESS' if all_success else 'FAILED'
        run.finished_at = timezone.now()
        run.save()
        logger.info(f"Pipeline {run.id} finalized: {run.status}")
    except Exception as e:
        logger.error(f"Error finalizing pipeline {pipeline_run_id}: {e}")
    return f"Pipeline {pipeline_run_id} finalized"

def orchestrate_pipeline(profile_id, run_id=None):
    """Constructs a Celery chain based on the BuildProfile."""
    profile = BuildProfile.objects.get(id=profile_id)
    tasks = []

    if profile.headless:
        # Use .si (immutable) so the previous result isn't passed as an argument
        tasks.append(run_headless_tests_task.si(run_id))

    if profile.staging:
        tasks.append(run_staging_build_task.si(run_id))

    if not tasks:
        return None

    # Finalize task to update the run status. 
    # Note: Even with .si() in tasks, the last task's result is passed to the next in a chain.
    # So finalize_pipeline_run still needs to accept the result of the last build task.
    if run_id:
        return chain(*tasks, finalize_pipeline_run.si(run_id))
    
    return chain(*tasks)
