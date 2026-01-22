"""Native Hydra spell for version stamping Unreal Engine projects."""

import datetime
import getpass
import json
import os
import time
from typing import Any, Dict, Tuple

from hydra.models import HydraHead
from hydra.spells.spell_casters.spell_handlers.spell_handler_codes import HANDLER_INTERNAL_ERROR_CODE, HANDLER_SUCCESS_CODE, \
    HANDLER_WRITE_ERROR_CODE
from hydra.spells.spell_casters.switches_and_arguments import spell_switches_and_arguments
from hydra.utils import log_system

_DEFAULT_INDENT = 4
_ENCODING = 'utf-8'
_DEFAULT_GAME_NAME = 'HSH: Vacancy'


def update_version_metadata(head_id: int) -> Tuple[int, str]:
    """Updates the application version JSON file with build metadata.

    Args:
        head_id: int: The HydraHead execution context.

    Returns:
        Tuple[int, str]: (exit_code, log_output)
            exit_code = 0 for success, 1 for failure
    """
    head = HydraHead.objects.get(id=head_id)
    spell = head.spell
    app_version_file = spell_switches_and_arguments(spell.id)
    target_path = os.path.normpath(app_version_file)

    log = [f"=== NATIVE VERSION STAMPER ===", f"Target: {target_path}"]
    log_system(head, f"Starting version stamp on {target_path}")

    directory = os.path.dirname(os.path.abspath(target_path))
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            log.append(f"Created directory: {directory}")
        except Exception as e:
            log.append(f"[ERROR] Could not create directory {directory}: {e}")
            return HANDLER_WRITE_ERROR_CODE, "\n".join(log)

    data: Dict[str, Any] = dict()
    if os.path.exists(target_path):
        with open(target_path, 'r', encoding=_ENCODING) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                log.append(f"[WARNING] {target_path} is corrupt. Re-initializing.")

    timestamp = int(time.time())
    hex_hash = hex(timestamp)[2:].upper()
    now = datetime.datetime.now()

    build_meta = {
        'Hash': hex_hash,
        'Date': now.strftime('%Y-%m-%d %H:%M:%S'),
        'DayOfYear': now.timetuple().tm_yday,
        'Builder': getpass.getuser(),
    }
    data['Build'] = build_meta

    log.append(f"  > Hash:    {build_meta['Hash']}")
    log.append(f"  > Date:    {build_meta['Date']}")
    log.append(f"  > Builder: {build_meta['Builder']}")

    if 'Game' not in data:
        data['Game'] = {
            'Name': _DEFAULT_GAME_NAME,
            'Major': 0, 'Minor': 0, 'Patch': 0, 'Label': 'DEV'
        }

    if 'Target' not in data:
        data['Target'] = {'Environment': 'Production', 'Store': 'Steam'}

    try:
        with open(target_path, 'w', encoding=_ENCODING) as f:
            json.dump(data, f, indent=_DEFAULT_INDENT)

        log.append('[SUCCESS] Version Stamp Applied.')
        return HANDLER_SUCCESS_CODE, "\n".join(log)

    except Exception as e:
        log.append(f'[ERROR] Version Stamp Failed: {str(e)}')
        return HANDLER_INTERNAL_ERROR_CODE, '\n'.join(log)
