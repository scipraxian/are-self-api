import time
import logging
from talos_agent.utils.client import TalosAgentClient
from core.models import RemoteTarget
from hydra.models import HydraHeadStatus, HydraHead

logger = logging.getLogger(__name__)


def remote_launch_native(head):
    """
    Native handler to launch a process on a remote agent and stream logs.
    Implements 'Authoritative Writer' pattern to match Local Execution.
    """
    # Init Log Buffer (In-Memory Source of Truth)
    log_buffer = [head.spell_log or f"=== REMOTE LAUNCH DIAGNOSTICS ==="]

    def flush_log():
        """Writes memory buffer to DB."""
        try:
            full_content = "".join(log_buffer)
            # Update ONLY the spell_log field
            HydraHead.objects.filter(pk=head.pk).update(spell_log=full_content)
        except Exception as e:
            logger.error(f"Failed to flush remote logs: {e}")

    def append_log(msg):
        log_buffer.append(msg)

    # 1. Selection Logic
    target = RemoteTarget.objects.filter(is_enabled=True, status='ONLINE').first()
    if not target:
        append_log("\n[FATAL] No ONLINE agents available.")
        flush_log()
        return 1, "".join(log_buffer)

    client = TalosAgentClient(target.ip_address or target.hostname, port=target.agent_port)

    exe_path = target.remote_exe_path
    log_path = target.remote_log_path

    append_log(f"\nTarget: {target.hostname} ({client.host})")
    append_log(f"\nExe: {exe_path}")
    append_log(f"\nLog: {log_path}\n")

    if not exe_path:
        append_log("\n[FATAL] Agent has no remote_exe_path configured.")
        flush_log()
        return 1, "".join(log_buffer)

    # 2. Launch
    params = ["-server", "-log", "-windowed", "-resX=1280", "-resY=720"]

    head.status_id = HydraHeadStatus.RUNNING
    head.save(update_fields=['status'])
    append_log(f"Launching with params: {params}\n")
    flush_log()

    res = client.launch(exe_path, params)
    if res.get('status') != 'LAUNCHED':
        append_log(f"\n[ERROR] Agent launch failed: {res.get('message')}")
        flush_log()
        return 1, "".join(log_buffer)

    append_log(f"Process LAUNCHED. Connecting to stream...\n")
    flush_log()

    # 3. Stream Logs (Authoritative)
    if log_path:
        try:
            last_save = time.time()

            # This generator yields lines as they arrive from the agent
            for line in client.stream_logs(log_path):
                # The agent sends JSON lines, client.stream_logs yields raw text content
                append_log(line)  # line already includes newline from the file usually?
                # If stream_logs strips newline, add it back:
                if not line.endswith('\n'):
                    append_log('\n')

                # Lightweight Stop Check
                status = HydraHead.objects.filter(pk=head.pk).values_list('status', flat=True).first()
                if status == HydraHeadStatus.FAILED:
                    # We can't easily kill the remote process from here without a new client call
                    # But we can stop listening.
                    append_log("\n[STOP] Terminated by User (Stream Disconnected).")
                    flush_log()
                    return 1, "".join(log_buffer)

                # Batch Save (1s)
                if (time.time() - last_save > 1.0):
                    flush_log()
                    last_save = time.time()

        except Exception as e:
            append_log(f"\n[ERROR] Stream interrupted: {e}")
            flush_log()

    append_log("\n[REMOTE] Execution finished or stream closed.")
    flush_log()
    return 0, "".join(log_buffer)