import os
import subprocess
import logging
import time
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

def stream_process_with_log_tail(cmd, step, log_file_path):
    """
    Runs a command and streams BOTH stdout and a specific target log file 
    to the database in real-time.
    """
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding='utf-8',
        errors='replace'
    )

    log_buffer = []
    file_cursor = 0
    
    # If the file exists from a previous run, start at the END to avoid duplicating old logs
    # UNLESS the file is smaller than before (new run overwrote it), then start at 0.
    if os.path.exists(log_file_path):
        file_cursor = 0 # Unreal overwrites on start, so we start at 0 to catch the new header
    
    def flush_logs():
        if log_buffer:
            current_text = "".join(log_buffer)
            if step.logs:
                step.logs += current_text
            else:
                step.logs = current_text
            step.save()
            log_buffer.clear()

    while True:
        retcode = process.poll()
        
        # 1. Read Console (Launcher)
        try:
            # Non-blocking check for stdout
            lines = process.stdout.readline()
            if lines:
                log_buffer.append(lines)
        except Exception:
            pass
            
        # 2. Read Game Log (HSHVacancy.log)
        if os.path.exists(log_file_path):
            try:
                with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(file_cursor)
                    new_data = f.read()
                    if new_data:
                        log_buffer.append(new_data)
                        file_cursor = f.tell()
            except (PermissionError, OSError):
                pass # File locked by UE5, skip this tick
        
        flush_logs()

        if retcode is not None:
            # Final sweep
            remaining = process.stdout.read()
            if remaining: log_buffer.append(remaining)
            flush_logs()
            break
        
        time.sleep(0.5)

    return retcode

@shared_task(bind=True, max_retries=3, default_retry_delay=1)
def run_headless_tests_task(self, pipeline_run_id=None):
    run = None
    step = None
    
    if pipeline_run_id:
        try:
            run = PipelineRun.objects.get(id=pipeline_run_id)
        except PipelineRun.DoesNotExist:
            return self.retry(exc=PipelineRun.DoesNotExist())

        step = PipelineStepRun.objects.create(
            pipeline_run=run,
            step_name="Headless Validator",
            status='RUNNING'
        )

    env = get_active_env()
    if not env:
        if step:
            step.status = 'FAILED'
            step.logs = "No Active Environment"
            step.save()
        return "FAILED"

    uproject_path = os.path.join(env.project_root, f"{env.project_name}.uproject")
    editor_cmd = os.path.join(env.engine_root, 'Engine', 'Binaries', 'Win64', 'UnrealEditor-Cmd.exe')
    
    # --- LOG PATH LOGIC ---
    # Target: .../Saved/Logs/HSHVacancy.log
    target_log_file = os.path.join(env.project_root, 'Saved', 'Logs', f'{env.project_name}.log')

    if step:
        step.logs = f"--- ORCHESTRATOR START ---\nTarget Log: {target_log_file}\n"
        step.save()

    test_args = [
        editor_cmd,
        uproject_path,
        '-log',
        '-nullrhi',
        '-unattended',
        '-nopause',
        '-CustomConfig=Staging',
        '-ExecCmds=Automation RunTests HSH.Tests; Quit',
        '-TestExit=Automation Test Queue Empty',
    ]
    
    retcode = stream_process_with_log_tail(test_args, step, target_log_file)

    if retcode != 0:
        if step:
            step.status = 'FAILED'
            step.finished_at = timezone.now()
            step.save()
        return f"FAILED: Code {retcode}"
    
    if step:
        step.status = 'SUCCESS'
        step.finished_at = timezone.now()
        step.save()
    return "SUCCESS"

@shared_task
def run_staging_build_task(pipeline_run_id=None):
    # Same pattern for Staging, but target UAT log if desired
    # For now, standard implementation
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
        if step: step.status='FAILED'; step.save()
        return "FAILED"

    uproject_path = os.path.join(env.project_root, f"{env.project_name}.uproject")
    uat_batch = os.path.join(env.engine_root, 'Engine', 'Build', 'BatchFiles', 'RunUAT.bat')
    staging_dir = env.staging_dir or os.path.join(env.build_root, 'Staging')

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
    
    # We can also stream this one simply
    # For UAT, the log is usually stdout, so we just capture stdout
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=True
    )
    
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output and step:
            step.logs += output
            # Throttle saves slightly to avoid DB locking
            # (In production, use Redis cache for this buffer)
            step.save()
            
    if process.poll() != 0:
        if step:
            step.status = 'FAILED'
            step.finished_at = timezone.now()
            step.save()
        return "FAILED"
    
    if step:
        step.status = 'SUCCESS'
        step.finished_at = timezone.now()
        step.save()
    return "SUCCESS"

@shared_task
def finalize_pipeline_run(pipeline_run_id):
    logger.info(f"Finalizing PipelineRun {pipeline_run_id}")
    try:
        run = PipelineRun.objects.get(id=pipeline_run_id)
        all_success = all(s.status == 'SUCCESS' for s in run.steps.all())
        run.status = 'SUCCESS' if all_success else 'FAILED'
        run.finished_at = timezone.now()
        run.save()
    except Exception as e:
        logger.error(f"Error finalizing: {e}")
    return f"Pipeline {pipeline_run_id} finalized"

def orchestrate_pipeline(profile_id, run_id=None):
    profile = BuildProfile.objects.get(id=profile_id)
    tasks = []

    if profile.headless:
        tasks.append(run_headless_tests_task.si(run_id))

    if profile.staging:
        tasks.append(run_staging_build_task.si(run_id))

    if not tasks:
        return None

    if run_id:
        return chain(*tasks, finalize_pipeline_run.si(run_id))
    
    return chain(*tasks)
