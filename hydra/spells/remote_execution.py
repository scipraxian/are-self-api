import time
import logging
import json
from talos_agent.utils.client import TalosAgentClient
from core.models import RemoteTarget
from hydra.models import HydraHeadStatus

logger = logging.getLogger(__name__)


def remote_launch_native(head):
    """
    Native handler to launch a process on a remote agent and stream logs.
    Relies on Agent v2.1.5+ to handle log file waiting and buffering.
    """
    # 1. Selection Logic
    target = RemoteTarget.objects.filter(is_enabled=True,
                                         status='ONLINE').first()
    if not target:
        return 1, "Error: No ONLINE agents available for remote launch."

    client = TalosAgentClient(target.ip_address or target.hostname,
                              port=target.agent_port)

    exe_path = target.remote_exe_path
    log_path = target.remote_log_path

    if not exe_path:
        return 1, f"Error: Agent {target.hostname} has no remote_exe_path configured."

    # 2. Launch
    # We explicitly pass -log to ensure the file is generated
    params = ["-server", "-log", "-windowed", "-resX=1280", "-resY=720"]

    head.spell_log = f"=== REMOTE LAUNCH ===\nTarget: {target.hostname} ({client.host})\nExe: {exe_path}\nLog: {log_path}\n\n"
    head.status_id = HydraHeadStatus.RUNNING
    head.save()

    res = client.launch(exe_path, params)
    if res.get('status') != 'LAUNCHED':
        return 1, f"Error: Agent failed to launch: {res.get('message')}"

    head.spell_log += f"Process LAUNCHED. Connecting to log stream...\n"
    head.save()

    # 3. Stream Logs (Passive Mode)
    # The agent will block until the file exists, then push data.
    if log_path:
        try:
            last_save = time.time()
            log_buffer = []

            # Client.stream_logs yields lines as they arrive
            for line in client.stream_logs(log_path):
                log_buffer.append(line)

                # Batch updates to DB to avoid thrashing (1s interval)
                if time.time() - last_save > 1.0:
                    head.refresh_from_db()

                    # TERMINATION CHECK (Stop Button)
                    if head.status_id == HydraHeadStatus.FAILED:
                        # We don't need to do anything here, the terminate() signal
                        # will have killed the process. We just stop listening.
                        return 1, head.spell_log + "\n[REMOTE] Stream disconnected by User."

                    if log_buffer:
                        head.spell_log += "\n".join(log_buffer) + "\n"
                        head.save()
                        log_buffer = []
                        last_save = time.time()

            # Flush remaining buffer on exit
            if log_buffer:
                head.spell_log += "\n".join(log_buffer) + "\n"
                head.save()

        except Exception as e:
            head.spell_log += f"\n[ERROR] Log streaming interrupted: {e}"
            head.save()

    return 0, head.spell_log + "\n[REMOTE] Stream ended normally."