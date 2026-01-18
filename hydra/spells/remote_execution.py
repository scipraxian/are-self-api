import time
import logging
from talos_agent.utils.client import TalosAgentClient
from core.models import RemoteTarget
from hydra.models import HydraHeadStatus

logger = logging.getLogger(__name__)


def remote_launch_native(head):
    """
    Native handler to launch a process on a remote agent and stream logs.
    Targets the first available ONLINE agent.
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
    # We might want to pass specific params for a server, e.g. -server -log
    params = ["-server", "-log", "-windowed", "-resX=1280", "-resY=720"]

    head.spell_log = f"=== REMOTE LAUNCH ===\nTarget: {target.hostname} ({client.host})\nExe: {exe_path}\nParams: {params}\n\n"
    head.status_id = HydraHeadStatus.RUNNING
    head.save()

    res = client.launch(exe_path, params)
    if res.get('status') != 'LAUNCHED':
        return 1, f"Error: Agent failed to launch: {res.get('message')}"

    head.spell_log += f"Process LAUNCHED on agent. Attaching to log: {log_path}\n"
    head.save()

    # 3. Stream Logs
    # Note: This is running inside a Celery worker.
    # We can block here and yield logs to the DB.
    if log_path:
        try:
            # We need a way to stop streaming if the head is terminated.
            # But for now, simple loop.
            last_save = time.time()
            log_buffer = []

            for line in client.stream_logs(log_path):
                log_buffer.append(line)

                # Check for termination? (Maybe check DB status)
                if time.time() - last_save > 1.0:
                    head.refresh_from_db()
                    if head.status_id == HydraHeadStatus.FAILED:
                        # Terminated
                        return 1, head.spell_log + "\n[REMOTE] Streaming terminated."

                    if log_buffer:
                        head.spell_log += "\n".join(log_buffer) + "\n"
                        head.save()
                        log_buffer = []
                        last_save = time.time()

                # Check if process died on agent side?
                # The agent stream_logs generator might close if the connection drops.

        except Exception as e:
            head.spell_log += f"\n[ERROR] Log streaming interrupted: {e}"
            head.save()

    return 0, head.spell_log + "\n[REMOTE] Execution finished or detached."
