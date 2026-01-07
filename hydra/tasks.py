import collections
import subprocess
import threading
import queue
import time
import os
import datetime
from celery import shared_task
from django.db import transaction
from .models import HydraHead, HydraHeadStatus

# Rigid context structure
HydraContext = collections.namedtuple('HydraContext', [
    'project_root',
    'engine_root',
    'build_root',
    'staging_dir',
    'project_name',
    'dynamic_context'
])

def get_timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")

def log_system(head, message):
    """Helper to append to execution_log and save immediately."""
    entry = f"[{get_timestamp()}] {message}\n"
    # we fetch a fresh copy to avoid overwriting spell_log stream updates
    # or just append safely since we are the primary writer
    head.execution_log += entry
    head.save(update_fields=['execution_log'])

def resolve_template(template_str, context: HydraContext):
    if not template_str: return ""
    format_data = context._asdict()
    if context.dynamic_context:
        format_data.update(context.dynamic_context)
    try:
        return template_str.format(**format_data)
    except KeyError:
        return template_str

def build_command(hydra_head):
    spawn = hydra_head.spawn
    env = spawn.environment.project_environment
    spell = hydra_head.spell
    exe = spell.executable
    
    context = HydraContext(
        project_root=env.project_root,
        engine_root=env.engine_root,
        build_root=env.build_root,
        staging_dir=env.staging_dir or "",
        project_name=env.project_name,
        dynamic_context={} 
    )

    # 1. Resolve & Normalize Exe Path
    raw_exe_path = resolve_template(exe.path_template, context)
    exe_path = os.path.normpath(raw_exe_path)
    cmd = [exe_path]
    
    # 2. Append Switches
    for switch in spell.active_switches.all():
        flag_str = resolve_template(switch.flag, context)
        val_str = ""
        if switch.value:
            val_str = resolve_template(switch.value, context)

        if val_str:
            if flag_str.endswith('='):
                cmd.append(f"{flag_str}{val_str}")
            elif not flag_str:
                cmd.append(val_str)
            else:
                cmd.append(flag_str)
                cmd.append(val_str)
        else:
            if flag_str:
                if " " in flag_str:
                    cmd.extend(flag_str.split())
                else:
                    cmd.append(flag_str)
            
    return cmd

def stream_command_to_db(cmd, head):
    """
    Executes command and flushes STDOUT/STDERR to DB every ~2s.
    """
    head.status_id = HydraHeadStatus.RUNNING
    pretty_cmd = " ".join([f'"{c}"' if " " in c else c for c in cmd])
    
    head.spell_log = f"=== LAUNCHING ===\nCmd: {pretty_cmd}\n\n"
    head.execution_log += f"[{get_timestamp()}] Initializing Process...\n"
    head.execution_log += f"[{get_timestamp()}] Command constructed ({len(cmd)} tokens).\n"
    head.save()

    cwd = head.spawn.environment.project_environment.project_root
    log_system(head, f"Working Directory: {cwd}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
            cwd=cwd
        )
        log_system(head, f"Process Spawned. PID: {process.pid}")
    except Exception as e:
        log_system(head, f"FATAL ERROR: Failed to launch process: {e}")
        head.spell_log += f"\n[FATAL] Failed to launch: {e}"
        head.status_id = HydraHeadStatus.FAILED
        head.save()
        return -1

    q = queue.Queue()
    def reader():
        try:
            for line in iter(process.stdout.readline, ''):
                q.put(line)
        finally:
            process.stdout.close()
    
    t = threading.Thread(target=reader, daemon=True)
    t.start()

    log_buffer = []
    last_save = time.time()
    
    while True:
        alive = process.poll() is None
        while True:
            try:
                line = q.get_nowait()
                log_buffer.append(line)
            except queue.Empty:
                break
        
        if (time.time() - last_save > 2.0) or (len(log_buffer) > 20):
            if log_buffer:
                chunk = "".join(log_buffer)
                head.spell_log += chunk
                head.save()
                log_buffer = []
                last_save = time.time()
        
        if not alive and q.empty():
            break
        time.sleep(0.1)

    if log_buffer:
        head.spell_log += "".join(log_buffer)
        head.save()

    log_system(head, f"Process finished with Exit Code: {process.returncode}")
    return process.returncode

@shared_task
def check_next_wave(spawn_id):
    from .hydra import Hydra
    controller = Hydra(spawn_id=spawn_id)
    controller._dispatch_next_wave()

@shared_task(bind=True)
def cast_hydra_spell(self, hydrahead_id):
    try:
        head = HydraHead.objects.get(id=hydrahead_id)
        head.celery_task_id = self.request.id
        head.save()
        
        cmd = build_command(head)
        retcode = stream_command_to_db(cmd, head)
        
        head.result_code = retcode
        if retcode == 0:
            head.status_id = HydraHeadStatus.SUCCESS
            head.spell_log += "\n\n[SUCCESS] Spell Completed."
        else:
            head.status_id = HydraHeadStatus.FAILED
            head.spell_log += f"\n\n[FAILURE] Exited with code {retcode}."
            
        head.save()
        
        if retcode == 0:
            transaction.on_commit(lambda: check_next_wave.delay(head.spawn.id))
        
        return f"Spell {head.spell.name} finished: {retcode}"
        
    except Exception as e:
        try:
            head = HydraHead.objects.get(id=hydrahead_id)
            head.status_id = HydraHeadStatus.FAILED
            log_system(head, f"INTERNAL EXCEPTION: {str(e)}")
            head.save()
        except:
            pass
        raise e