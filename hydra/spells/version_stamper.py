"""Native Hydra spell for version stamping Unreal Engine projects."""

import datetime
import getpass
import json
import os
import time
from typing import Any, Dict, List, Tuple

from hydra.models import HydraHead
from hydra.utils import HydraContext, resolve_template, log_system

_DEFAULT_INDENT = 4
_ENCODING = 'utf-8'

def version_stamp_native(head: HydraHead) -> Tuple[int, str]:
    """Updates the application version JSON file with build metadata.
    
    Args:
        head: The HydraHead execution context.
        
    Returns:
        Tuple[int, str]: (exit_code, log_output)
    """
    env = head.spawn.environment.project_environment
    spell = head.spell
    
    # 1. Prepare Context
    context = HydraContext(
        project_root=env.project_root,
        engine_root=env.engine_root,
        build_root=env.build_root,
        staging_dir=env.staging_dir or "",
        project_name=env.project_name,
        dynamic_context={}
    )
    
    # 2. Determine Target File Path (from Switches or Default)
    # We look for a switch that might provide the path.
    target_path_template = "{project_root}/Content/AppVersion.json"
    for switch in spell.active_switches.all():
        if switch.flag == "--path":
            target_path_template = switch.value
            break
            
    raw_target_path = resolve_template(target_path_template, context)
    target_path = os.path.normpath(raw_target_path)
    
    log = [f"=== NATIVE VERSION STAMPER ===", f"Target: {target_path}"]
    log_system(head, f"Starting version stamp on {target_path}")

    try:
        # 3. Ensure Directory Exists
        directory = os.path.dirname(os.path.abspath(target_path))
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            log.append(f"Created directory: {directory}")

        # 4. Load Existing Data
        data: Dict[str, Any] = {}
        if os.path.exists(target_path):
            try:
                with open(target_path, 'r', encoding=_ENCODING) as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                log.append(f"[WARNING] {target_path} is corrupt. Re-initializing.")

        # 5. Generate Build Metadata
        timestamp = int(time.time())
        hex_hash = hex(timestamp)[2:].upper()
        now = datetime.datetime.now()
        
        build_meta = {
            'Hash': hex_hash,
            'Date': now.strftime('%Y-%m-%d %H:%M:%S'),
            'DayOfYear': now.timetuple().tm_yday,
            'Builder': getpass.getuser(),
        }
        
        log.append(f"  > Hash:    {build_meta['Hash']}")
        log.append(f"  > Date:    {build_meta['Date']}")
        log.append(f"  > Builder: {build_meta['Builder']}")

        # 6. Update Structure
        if 'Game' not in data:
            data['Game'] = {
                'Name': env.project_name or 'HSH: Vacancy',
                'Major': 0, 'Minor': 0, 'Patch': 0, 'Label': 'DEV'
            }

        data['Build'] = build_meta

        if 'Target' not in data:
            data['Target'] = {'Environment': 'Production', 'Store': 'Steam'}

        # 7. Save to Disk
        with open(target_path, 'w', encoding=_ENCODING) as f:
            json.dump(data, f, indent=_DEFAULT_INDENT)
            
        log.append("[SUCCESS] Version Stamp Applied.")
        return 0, "\n".join(log)

    except Exception as e:
        log.append(f"[ERROR] Version Stamp Failed: {str(e)}")
        return 1, "\n".join(log)
