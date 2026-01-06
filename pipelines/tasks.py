import os
import subprocess
import json
import logging
import time
import threading
import queue
from celery import shared_task, chain
from django.utils import timezone
from environments.models import ProjectEnvironment
from pipelines.models import BuildProfile, PipelineRun, PipelineStepRun

logger = logging.getLogger(__name__)

def get_active_env():
    try:
        return ProjectEnvironment.objects.get(is_active=True)
    except ProjectEnvironment.DoesNotExist:
        return None

def parse_ue5_test_report(json_path):
    if not os.path.exists(json_path):
        return "\n--- NO TEST REPORT FOUND (Check index.json) ---\n"
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except Exception as e:
        return f"\n--- ERROR PARSING REPORT: {e} ---\n"

    passed = 0
    failed = 0
    tests = data.get('tests', [])
    output_lines = ["", "=" * 80, " TEST RESULTS SUMMARY", "=" * 80, f"{'TEST NAME':<60} | {'STATUS':<10} | {'TIME (s)':<10}", "-" * 80]

    for test in tests:
        full_path = test.get('fullTestPath', 'Unknown')
        state = test.get('state', 'Unknown')
        duration = test.get('duration', 0.0)
        status_str = 'PASS' if state == 'Success' else 'FAIL'
        if state == 'Success': passed += 1
        else: failed += 1
        
        display_path = full_path
        if len(display_path) > 57: display_path = "..." + display_path[-54:]
        output_lines.append(f"{display_path:<60} | {status_str:<10} | {duration:.4f}")

        if state != 'Success':
            for entry in test.get('entries', []):
                event = entry.get('event')
                if isinstance(event, dict) and event.get('type') == 'Error':
                    output_lines.append(f"    >>> ERROR: {event.get('message', 'No message')}")

    output_lines.append("-" * 80)
    output_lines.append(f"TOTAL: {len(tests)}  |  PASSED: {passed}  |  FAILED: {failed}")
    output_lines.append("=" * 80 + "\n")
    return "\n".join(output_lines)

def stream_process_with_log_tail(cmd, step, log_file_path):
    # 1. HEADER
    cmd_str = " ".join(cmd)
    header = (f"=== EXECUTION CONTEXT ===\nCmd: {cmd[0]}\nArgs: {cmd_str}\nTarget Log: {log_file_path}\n=========================\n\n")
    
    if step:
        # Overwrite the "Waiting..." text from the view
        step.logs = header
        step.status = 'RUNNING'
        step.save()

    print(f"[TASK] Launching: {cmd[0]}")
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding='utf-8', errors='replace')
    except FileNotFoundError:
        if step:
            step.logs += f"\n[FATAL] Executable not found: {cmd[0]}"
            step.status = 'FAILED'
            step.save()
        return -1

    console_queue = queue.Queue()
    def reader_thread(pipe, q):
        try:
            with pipe:
                for line in iter(pipe.readline, ''): q.put(line)
        finally: q.put(None)

    t = threading.Thread(target=reader_thread, args=(process.stdout, console_queue))
    t.daemon = True
    t.start()

    log_buffer = []
    file_cursor = 0
    # If log exists, start at beginning to catch everything for this run
    if os.path.exists(log_file_path): file_cursor = 0

    def flush_logs():
        if log_buffer:
            chunk = "".join(log_buffer)
            if step:
                if step.logs: step.logs += chunk
                else: step.logs = chunk
                step.save()
            log_buffer.clear()

    while True:
        process_alive = (process.poll() is None)
        while True:
            try:
                line = console_queue.get_nowait()
                if line is None: break
                log_buffer.append(line)
            except queue.Empty: break
        
        if os.path.exists(log_file_path):
            try:
                with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(file_cursor)
                    new_data = f.read()
                    if new_data:
                        log_buffer.append(new_data)
                        file_cursor = f.tell()
            except (PermissionError, OSError): pass

        flush_logs()
        
        if not process_alive and console_queue.empty():
            if os.path.exists(log_file_path):
                try:
                    with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                        f.seek(file_cursor)
                        log_buffer.append(f.read())
                except: pass
            flush_logs()
            break
        time.sleep(1.0)

    return process.returncode

@shared_task(bind=True, max_retries=3, default_retry_delay=1)
def run_headless_tests_task(self, pipeline_run_id=None):
    run = None
    step = None
    
    if pipeline_run_id:
        try:
            run = PipelineRun.objects.get(id=pipeline_run_id)
        except PipelineRun.DoesNotExist:
            return self.retry(exc=PipelineRun.DoesNotExist())
        
        # FIND THE PRE-CREATED STEP
        step = run.steps.filter(step_name="Headless Validator").first()
        if not step:
            # Fallback if view didn't create it
            step = PipelineStepRun.objects.create(pipeline_run=run, step_name="Headless Validator", status='RUNNING', logs="Initializing...")

    env = get_active_env()
    if not env:
        if step: step.status='FAILED'; step.logs="No Active Env"; step.save()
        return "FAILED"

    uproject_path = os.path.join(env.project_root, f"{env.project_name}.uproject")
    editor_cmd = os.path.join(env.engine_root, 'Engine', 'Binaries', 'Win64', 'UnrealEditor-Cmd.exe')
    
    # STRICT PATH: Saved/Logs/{ProjectName}.log
    log_folder = os.path.join(env.project_root, 'Saved', 'Logs')
    target_log_file = os.path.join(log_folder, f'{env.project_name}.log')

    test_args = [
        editor_cmd, uproject_path,
        '-log', '-nullrhi', '-unattended', '-nopause', '-nosplash', '-stdout', '-FullStdOutLogOutput',
        '-CustomConfig=Staging',
        f'-ReportExportPath={log_folder}',
        '-ExecCmds=Automation RunTests HSH.Tests; Quit',
        '-TestExit=Automation Test Queue Empty',
    ]
    
    retcode = stream_process_with_log_tail(test_args, step, target_log_file)

    if retcode == 0:
        report_json = os.path.join(log_folder, 'index.json')
        summary = parse_ue5_test_report(report_json)
        if step:
            step.logs += summary
            step.save()

    final_status = 'SUCCESS' if retcode == 0 else 'FAILED'
    if step:
        step.status = final_status
        step.finished_at = timezone.now()
        step.save()
        
    return f"{final_status}: Code {retcode}"

@shared_task
def run_staging_build_task(pipeline_run_id=None):
    run = None
    step = None
    if pipeline_run_id:
        try: run = PipelineRun.objects.get(id=pipeline_run_id)
        except: return None
        # FIND THE PRE-CREATED STEP
        step = run.steps.filter(step_name="Staging Builder").first()
        if not step:
            step = PipelineStepRun.objects.create(pipeline_run=run, step_name="Staging Builder", status='RUNNING', logs="Initializing...")

    env = get_active_env()
    uproject_path = os.path.join(env.project_root, f"{env.project_name}.uproject")
    uat_batch = os.path.join(env.engine_root, 'Engine', 'Build', 'BatchFiles', 'RunUAT.bat')
    staging_dir = env.staging_dir or os.path.join(env.build_root, 'Staging')

    cmd = [
        uat_batch, 'BuildCookRun',
        f'-project={uproject_path}',
        '-platform=Win64', '-clientconfig=Development', '-serverconfig=Development',
        '-build', '-cook', '-stage', '-pak',
        f'-stagingdirectory={staging_dir}',
        '-nocompileeditor', '-unattended', '-nopause', '-utf8output'
    ]
    
    uat_log = os.path.join(os.getenv('APPDATA'), 'Unreal Engine', 'AutomationTool', 'Logs', 'C+Program+Files+Epic+Games+UE_5.6', 'Log.txt')
    retcode = stream_process_with_log_tail(cmd, step, uat_log)
    
    final_status = 'SUCCESS' if retcode == 0 else 'FAILED'
    if step:
        step.status = final_status
        step.finished_at = timezone.now()
        step.save()
    return final_status

@shared_task
def finalize_pipeline_run(pipeline_run_id):
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
    if profile.headless: tasks.append(run_headless_tests_task.si(run_id))
    if profile.staging: tasks.append(run_staging_build_task.si(run_id))
    if not tasks: return None
    if run_id: return chain(*tasks, finalize_pipeline_run.si(run_id))
    return chain(*tasks)