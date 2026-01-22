import concurrent.futures
import subprocess
import os
import logging
import re
from core.models import RemoteTarget

logger = logging.getLogger(__name__)

def deploy_release_test(head):
    """
    Native distribution logic.
    Mirrors the Project Environment's staging/build location to the fleet.
    Auto-constructs destination paths by projecting the local path onto the remote agent.
    Defaults to standard 'steambuild' share if UNC path is not explicitly configured.
    """
    env = head.spawn.environment.project_environment
    
    # 1. Resolve Source Path
    source_candidate = os.path.join(env.build_root, 'ReleaseTest')
    source_path = os.path.normpath(source_candidate)

    if not os.path.exists(source_path):
        if env.staging_dir and os.path.exists(env.staging_dir):
            source_path = os.path.normpath(env.staging_dir)
        else:
            log_err = [f"=== NATIVE DISTRIBUTION ===", f"[FATAL] Source path not found.", f"Checked: {source_candidate}", f"Checked: {env.staging_dir}"]
            return 1, "\n".join(log_err)

    log = [f"=== NATIVE DISTRIBUTION ===", f"Source: {source_path}"]

    # 2. Get Targets (Include BUSY agents as they can still receive files)
    all_enabled = RemoteTarget.objects.filter(is_enabled=True)
    targets = all_enabled.filter(status__in=['ONLINE', 'BUSY'])
    
    skipped = all_enabled.exclude(status__in=['ONLINE', 'BUSY'])
    if skipped.exists():
        log.append(f"[INFO] Skipping {skipped.count()} OFFLINE/ERROR targets: {[t.hostname for t in skipped]}")

    if not targets.exists():
        return 0, "\n".join(log + ["[SKIPPED] No ONLINE/BUSY targets found."])

    # 3. Define Exclusions
    excludes = ['Saved', 'Intermediate', '.git', 'FileOpenOrder', 'DerivedDataCache', 'PipelineCaches']
    log.append(f"Targets: {[t.hostname for t in targets]}")
    
    # 4. Parallel Execution
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_target = {
            executor.submit(_sync_target, t, source_path, env, excludes): t 
            for t in targets
        }
        
        for future in concurrent.futures.as_completed(future_to_target):
            target = future_to_target[future]
            try:
                success, msg = future.result()
                results.append((target.hostname, success, msg))
            except Exception as e:
                results.append((target.hostname, False, str(e)))

    # 5. Reporting
    fail_count = 0
    for host, success, msg in results:
        status_icon = "[OK]" if success else "[FAIL]"
        log.append(f"{status_icon} {host}: {msg}")
        if not success:
            fail_count += 1

    final_log = "\n".join(log)
    return (1 if fail_count > 0 else 0), final_log

def _parse_robocopy_summary(output):
    """
    Extracts 'Copied' Bytes from Robocopy summary table.
    Robustly handles units (g, m, k) separated by spaces.
    """
    for line in output.splitlines():
        if "Bytes :" in line:
            # Regex to find all size-like values in the line.
            # Matches: "3.54 g", "100", "150.2 m"
            # Pattern: Digits + (Optional Dot + Digits) + (Optional Space + Unit)
            matches = re.findall(r"(\d+(?:\.\d+)?\s*[tgmk]?)", line, re.IGNORECASE)
            
            # The matches list will contain all numbers found.
            # Index 0: Total
            # Index 1: Copied (This is the one we want)
            # Index 2: Skipped
            # ...
            if len(matches) >= 2:
                # Clean up multiple spaces if regex captured them
                return f"Transfer Size: {matches[1].strip()}"
                
    return "Transfer Size: 0 (No Summary)"

def _sync_target(target, source_path, env, excludes):
    """
    Helper: Robocopy wrapper.
    Calculates destination based on target configuration OR Project Environment adherence.
    """
    dest_path = target.unc_path

    # --- AUTO-CONFIGURATION (ADHERE TO PROJECT ENV) ---
    if not dest_path:
        # Fallback to standard project share 'steambuild' if manual UNC is missing.
        rel_path = ""
        norm_source = os.path.normpath(source_path)
        norm_build = os.path.normpath(env.build_root)
        norm_staging = os.path.normpath(env.staging_dir) if env.staging_dir else None

        if norm_source.startswith(norm_build):
            # Case A: Source is inside Build Root
            rel_path = os.path.relpath(norm_source, norm_build)
        elif norm_staging and norm_source.startswith(norm_staging):
            # Case B: Source is inside Staging Dir (and disjoint from BuildRoot)
            sub_path = os.path.relpath(norm_source, norm_staging)
            rel_path = os.path.join(os.path.basename(norm_staging), sub_path)
        else:
            # Case C: Fallback
            rel_path = os.path.basename(norm_source)

        rel_path = os.path.normpath(rel_path)
        dest_path = f"\\\\{target.hostname}\\steambuild\\{rel_path}"

    # CRITICAL: Robocopy /subprocess quirk. 
    # If a path ends in a backslash and is then quoted by subprocess, 
    # Robocopy sees \" and thinks it's an escaped quote.
    # We must ensure no trailing backslashes.
    source_path = source_path.rstrip('\\')
    dest_path = dest_path.rstrip('\\')

    # Robocopy /MIR requires the *directory* itself as destination
    cmd = [
        'robocopy',
        source_path,
        dest_path,
        '/MIR', '/MT:8', '/R:2', '/W:2',
        '/NFL', '/NDL', '/NJH', 
    ]
    
    if excludes:
        cmd.append('/XD')
        cmd.extend(excludes)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        # Robocopy Exit Codes: 0=No Change, 1=Files Copied, <8=Success
        if proc.returncode < 8:
            stats = _parse_robocopy_summary(proc.stdout)
            status_tag = "(Files Copied)" if proc.returncode >= 1 else "(Up to Date)"
            return True, f"Synced to {dest_path} {status_tag} | {stats}"
            
        # If it failed, let's at least see the first line of error or the return code
        err_hint = proc.stderr.splitlines()[0] if proc.stderr else "See Robocopy logs"
        return False, f"Robocopy Error {proc.returncode} ({dest_path}): {err_hint}"
    except Exception as e:
        return False, f"Sys Error: {e}"