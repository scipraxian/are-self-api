from hydra.spells.native_executables import NativeExecutables
import collections
import datetime
import os
import queue
import subprocess
import threading
import time

from celery import shared_task
from django.db import transaction

from .models import HydraHead
from .models import HydraHeadStatus
from .utils import get_timestamp
from .utils import HydraContext
from .utils import log_system
from .utils import resolve_template
    

def build_command(hydra_head):
    spawn = hydra_head.spawn
    env = spawn.environment.project_environment
    spell = hydra_head.spell
    exe = spell.executable

    context = HydraContext(project_root=env.project_root,
                           engine_root=env.engine_root,
                           build_root=env.build_root,
                           staging_dir=env.staging_dir or "",
                           project_name=env.project_name,
                           dynamic_context={})

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
        process = subprocess.Popen(cmd,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   text=True,
                                   bufsize=1,
                                   encoding='utf-8',
                                   errors='replace',
                                   cwd=cwd)
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
        try:
            head = HydraHead.objects.get(id=hydrahead_id)
        except HydraHead.DoesNotExist:
            return f"Task skipped: HydraHead {hydrahead_id} no longer exists."

        head.celery_task_id = self.request.id
        head.save()

        native_handler = NativeExecutables.get_handler(head.spell.executable.slug)
        
        if native_handler:
            # Native Execution Path
            head.status_id = HydraHeadStatus.RUNNING
            head.save()
            log_system(head, f"Dispatching Native Handler: {head.spell.executable.slug}")
            
            try:
                retcode, output_log = native_handler(head)
                head.spell_log = output_log
            except Exception as e:
                retcode = 1
                head.spell_log = f"Native Handler Exception: {str(e)}"
        else:
            # Legacy/Shell Execution Path
            # REMOVED LOCAL IMPORT causing UnboundLocalError
            cmd = build_command(head)
            retcode = stream_command_to_db(cmd, head)

        head.result_code = retcode
        if retcode == 0:
            head.status_id = HydraHeadStatus.SUCCESS
            head.spell_log += "\n\n[SUCCESS] Spell Completed."
            head.save()

            # Outcome Logic.... i moved this import due to: from partially initialized module 'talos_frontal.logic'
            from .outcomes import process_outcomes
            process_outcomes(head.id)

            # Check if outcome failed the head
            head.refresh_from_db()
            if head.status_id == HydraHeadStatus.FAILED:
                pass  # Already failed
            else:
                transaction.on_commit(
                    lambda: check_next_wave.delay(head.spawn.id))

        else:
            head.status_id = HydraHeadStatus.FAILED
            head.spell_log += f"\n\n[FAILURE] Exited with code {retcode}."
            head.save()

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
