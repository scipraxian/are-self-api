import os
import time
import subprocess
import logging
from hydra.models import HydraHeadStatus, HydraHead
from hydra.utils import resolve_template, HydraContext

logger = logging.getLogger(__name__)


def local_launch_native(head):
    """
    Robust Local Launcher.
    1. Captures launch timestamp.
    2. Launches process (with correct argument splitting).
    3. Waits for log file creation/update (Timestamp > LaunchTime).
    4. Streams logs using Authoritative Writer (No DB collisions).
    """
    # 1. Resolve Context & Paths
    env = head.spawn.environment.project_environment
    context = HydraContext(
        project_root=env.project_root,
        engine_root=env.engine_root,
        build_root=env.build_root,
        staging_dir=env.staging_dir or "",
        project_name=env.project_name,
        dynamic_context={}
    )

    # Capture Launch Timestamp for Stale File Detection
    # We only accept logs modified AFTER this moment.
    launch_start_time = time.time()

    # Init Log Buffer (In-Memory Source of Truth)
    log_buffer = [head.spell_log or f"=== LOCAL LAUNCH DIAGNOSTICS ==="]

    def flush_log():
        """Writes memory buffer to DB."""
        try:
            full_content = "".join(log_buffer)
            # Update ONLY the spell_log field
            HydraHead.objects.filter(pk=head.pk).update(spell_log=full_content)
        except Exception as e:
            logger.error(f"Failed to flush logs: {e}")

    def append_log(msg):
        log_buffer.append(msg)

    # Resolve executable
    exe_template = head.spell.executable.path_template
    if not exe_template:
        append_log("\n[WARNING] Template empty! Defaulting to ReleaseTest.")
        exe_template = "{build_root}/ReleaseTest/{project_name}.exe"

    exe_path = resolve_template(exe_template, context)
    exe_path = os.path.normpath(exe_path)
    append_log(f"\nExe: '{exe_path}'")

    # Determine Log Path
    exe_dir = os.path.dirname(exe_path)
    log_path = os.path.join(exe_dir, env.project_name, 'Saved', 'Logs', f"{env.project_name}.log")
    append_log(f"\nLog Target: '{log_path}'\n")

    # 2. Pre-Flight Checks
    if not os.path.exists(exe_path):
        append_log(f"[FATAL] Exe not found.")
        flush_log()
        return 1, "".join(log_buffer)

    if os.path.isdir(exe_path):
        append_log(f"[FATAL] Target is a DIRECTORY. Check path_template.")
        flush_log()
        return 1, "".join(log_buffer)

    # 3. Launch Process (With Argument Splitting Fix)
    cmd = [exe_path]
    for switch in head.spell.active_switches.all():
        flag = resolve_template(switch.flag, context)
        val = resolve_template(switch.value, context)

        # CRITICAL FIX: Split composite flags ("-windowed -resX=...")
        if flag:
            if " " in flag:
                cmd.extend(flag.split())
            else:
                cmd.append(flag)

        if val:
            cmd.append(val)

    if "-log" not in cmd: cmd.append("-log")

    # Reset DB Status
    head.status_id = HydraHeadStatus.RUNNING
    head.save(update_fields=['status'])
    append_log(f"Cmd: {cmd}\n\n")
    flush_log()

    try:
        proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        append_log(f"Process Spawned (PID: {proc.pid}). Waiting for NEW log file...\n")
        flush_log()
    except Exception as e:
        append_log(f"\n[CRASH] Launch Failed: {e}\n")
        flush_log()
        return 1, "".join(log_buffer)

    # 4. Tail Loop (Stale File Protection)
    # We wait until the log file's modification time is GREATER than our launch time.
    retries = 0
    log_found = False

    while not log_found:
        time.sleep(1)
        retries += 1

        # Check Process Life
        if proc.poll() is not None:
            append_log(f"\n[FATAL] Process died immediately (Exit {proc.returncode}). No new log generated.\n")
            flush_log()
            return 1, "".join(log_buffer)

        # Check File Freshness
        if os.path.exists(log_path):
            try:
                # Windows: getctime is creation, getmtime is modify.
                # UE usually recreates the file (creation time updates).
                # We check modification just to be safe.
                file_mtime = os.path.getmtime(log_path)

                # Allow a small clock skew buffer (0.5s) if filesystems are weird
                if file_mtime >= (launch_start_time - 1.0):
                    append_log(f"[CONNECTED] Found fresh log (Modified: {file_mtime} >= Launch: {launch_start_time})\n")
                    flush_log()
                    log_found = True
                    break
                else:
                    if retries % 5 == 0:
                        append_log(f"... Waiting for update (Stale log found from {file_mtime})...\n")
                        flush_log()
            except OSError:
                pass  # Locked? Retry.

        if retries > 30:
            append_log(f"[TIMEOUT] New log file never appeared after 30s.\n")
            flush_log()
            return 1, "".join(log_buffer)

    # 5. Stream (Authoritative)
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            last_save = time.time()

            while True:
                if proc.poll() is not None:
                    rest = f.read()
                    if rest: append_log(rest)
                    append_log(f"\n[LOCAL] Exited (Code {proc.returncode}).")
                    flush_log()
                    return proc.returncode, "".join(log_buffer)

                # Lightweight Stop Check
                status = HydraHead.objects.filter(pk=head.pk).values_list('status', flat=True).first()
                if status == HydraHeadStatus.FAILED:
                    proc.kill()
                    append_log("\n[STOP] Terminated by User.")
                    flush_log()
                    return 1, "".join(log_buffer)

                chunk = f.read()
                if chunk:
                    append_log(chunk)
                else:
                    time.sleep(0.1)

                if (time.time() - last_save > 1.0):
                    flush_log()
                    last_save = time.time()

    except Exception as e:
        append_log(f"\n[ERROR] Stream crashed: {e}")
        flush_log()
        return 1, "".join(log_buffer)