"""Celery tasks for core network operations and agent discovery."""

from celery import shared_task


@shared_task
def scan_network_task():
    """Orchestrates the network scan and syncs with config."""
    # # 1. Sync DB with builder_config.json first (Legacy support)
    # sync_targets_from_config()
    #
    # scanner = NetworkScanner()
    # found_agents = scanner.scan_subnet()
    #
    # # 2. Update OR Create for found agents with duplicate protection
    # for agent in found_agents:
    #   # Normalize hostname (strip domain)
    #   raw_hostname = agent['hostname']
    #   short_name = raw_hostname.split('.')[0].upper()
    #
    #   # Matching strategy:
    #   # 1. Exact IP match
    #   # 2. Exact hostname match
    #   # 3. Base hostname match (e.g. MIKE-DESK vs MIKE-DESK.lan)
    #   target = RemoteTarget.objects.filter(ip_address=agent['ip']).first()
    #
    #   if not target:
    #       target = RemoteTarget.objects.filter(hostname__iexact=raw_hostname).first()
    #   if not target:
    #       target = RemoteTarget.objects.filter(hostname__iexact=short_name).first()
    #   if not target:
    #       # Search for records where the hostname contains our short name or vice versa
    #       target = RemoteTarget.objects.filter(hostname__icontains=short_name).first()
    #
    #   if target:
    #     target.ip_address = agent['ip']
    #     # Prefer the short, clean name for the DB display
    #     target.hostname = short_name
    #     target.status = 'ONLINE'
    #     target.last_seen = timezone.now()
    #     target.save()
    #   else:
    #     # Create new with clean name
    #     RemoteTarget.objects.create(
    #         hostname=short_name,
    #         ip_address=agent['ip'],
    #         status='ONLINE',
    #         last_seen=timezone.now()
    #     )
    #
    # # 3. Trigger discovery for all online agents
    # for target in RemoteTarget.objects.filter(status='ONLINE'):
    #   discover_agent_assets_task.delay(target.id)
    #
    # return f'Scan completed. Found {len(found_agents)} active agents.'


@shared_task
def discover_agent_assets_task(target_id):
    """Probes the agent for project files and logs."""
    # target = RemoteTarget.objects.get(id=target_id)
    # if not target.ip_address: return "No IP for target"
    #
    # active_env = ProjectEnvironment.objects.filter(is_active=True).first()
    # if not active_env:
    #     active_env = ProjectEnvironment.objects.create(
    #         name="Default Auto-Generated Env",
    #         is_active=True,
    #         project_name='HSHVacancy',
    #         build_root="C:/steambuild"
    #     )
    #
    # pname = active_env.project_name or 'HSHVacancy'
    # root = active_env.build_root or 'C:/steambuild'
    #
    # client = TalosAgentClient(target.ip_address, port=target.agent_port)
    # print(f"[DISCOVERY] Probing {target.hostname} at {target.ip_address}")
    # print(f"[DISCOVERY] Using Project: {pname}, Base Root: {root}")
    #
    # # 1. Probe Build Root
    # res = client.probe_path(root)
    # print(f"[DISCOVERY] Root Probe Result: {res}")
    #
    # # Update version info
    # if res.get('version'):
    #     target.version = res['version']
    #     target.save()
    #
    # if not res.get('data', {}).get('exists'):
    #   # Try alternate root with ReleaseTest
    #   alt_root = os.path.join(root, "ReleaseTest").replace('\\', '/')
    #   print(f"[DISCOVERY] Primary root not found. Trying Alt Root: {alt_root}")
    #   res = client.probe_path(alt_root)
    #   print(f"[DISCOVERY] Alt Root Probe Result: {res}")
    #
    #   if res.get('data', {}).get('exists'):
    #       root = alt_root
    #       print(f"[DISCOVERY] Found root at: {root}")
    #   else:
    #       target.status = 'STORAGE_ERROR'
    #       target.is_exe_available = False
    #       target.save()
    #       err_msg = f"Discovery Failed for {target.hostname}. Paths tried: {active_env.build_root}, {alt_root}. Agent reported: {res}"
    #       print(f"[DISCOVERY] {err_msg}")
    #       return err_msg
    #
    # # 2. Strict Path Check based on Environment
    # # The user states: "searching is not required". We assume standard UE structure or direct root.
    # # Primary Candidate: {build_root}/{project_name}.exe (or Windows/{project_name}.exe for standard Staging)
    #
    # # Based on standard UE5 Staging:
    # # [StagingDir]/Windows/[Project].exe
    # # OR if build_root IS the Windows folder:
    # # [BuildRoot]/[Project].exe
    #
    # candidates = [
    #     f"ReleaseTest/{pname}.exe",            # Strict User Requirement
    #     f"{pname}.exe",                        # Direct in root
    #     f"Windows/{pname}.exe",                # Standard Staging
    #     f"WindowsNoEditor/{pname}.exe",        # Standard Package
    # ]
    #
    # print(f"[DISCOVERY] checking {len(candidates)} strict paths relative to {root}...")
    # exe_found = False
    #
    # for sub in candidates:
    #   full_path = os.path.join(root, sub).replace('\\', '/')
    #   probe = client.probe_path(full_path)
    #
    #   if probe.get('data', {}).get('exists') and not probe.get('data', {}).get('is_dir'):
    #     target.remote_exe_path = full_path
    #     target.is_exe_available = True
    #     if target.status != 'ONLINE': target.status = 'ONLINE'
    #     exe_found = True
    #
    #     # Strict Logs: Saved/Logs/[Project].log relative to exe or root
    #     # If exe is at C:/Build/Windows/Game.exe, logs are usually C:/Build/Windows/Game/Saved/Logs/Game.log
    #     exe_dir = os.path.dirname(full_path)
    #     log_path = f"{exe_dir}/{pname}/Saved/Logs/{pname}.log"
    #
    #     # Fallback: Check root logs if exe-relative missing (though strict implies we should know)
    #     if not client.probe_path(log_path).get('data', {}).get('exists'):
    #         print(f"[DISCOVERY] Log not found at strict path {log_path}, checking fallback...")
    #         log_path = f"{root}/Saved/Logs/{pname}.log"
    #
    #     target.remote_log_path = log_path
    #     print(f"[DISCOVERY] SUCCESS: Exe: {full_path} | Log: {log_path}")
    #     break
    #
    # if not exe_found:
    #     target.is_exe_available = False
    #     if target.status != 'ONLINE': target.status = 'ONLINE'
    #     print(f"[DISCOVERY] INFO: No executable found at expected paths (Root={root}, Project={pname}). Agent is ONLINE.")
    #
    # target.save()
    # return f"Discovery finished for {target.hostname}. Exe Available: {exe_found}"
