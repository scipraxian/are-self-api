"""Native Hydra spell for version stamping Unreal Engine projects."""

import datetime
import getpass
import json
import logging
import os
import time
from typing import Any, Dict, Tuple
from uuid import UUID

from central_nervous_system.models import HydraHead
from central_nervous_system.spells.spell_casters.spell_handlers.spell_handler_codes import (
    HANDLER_FILE_NOT_FOUND_CODE,
    HANDLER_INTERNAL_ERROR_CODE,
    HANDLER_PERMISSIONS_ERROR_CODE,
    HANDLER_SUCCESS_CODE,
    HANDLER_WRITE_ERROR_CODE,
)
from central_nervous_system.utils import (
    get_active_environment,
    log_system,
    resolve_environment_context,
)

logger = logging.getLogger(__name__)

_DEFAULT_INDENT = 4
_ENCODING = 'utf-8'
_DEFAULT_GAME_NAME = 'HSH: Vacancy'


def update_version_metadata(head_id: UUID) -> Tuple[int, str]:
    """Updates the application version JSON file with build metadata.

    Args:
        head_id: int: The HydraHead execution context.

    Returns:
        Tuple[int, str]: (exit_code, log_output)
            exit_code = 0 for success, 1 for failure
    """
    logging.info(f'Updating version metadata for head {head_id}...')
    head = HydraHead.objects.get(id=head_id)
    spell = head.spell

    env = get_active_environment(head)
    full_context = resolve_environment_context(head_id=head.id)

    full_cmd = spell.get_full_command(environment=env,
                                      extra_context=full_context)

    args_list = full_cmd[1:]
    if not args_list:
        return (
            HANDLER_INTERNAL_ERROR_CODE,
            'Error: No version file path provided in spell arguments.',
        )

    target_path = os.path.normpath(args_list[0])

    log = ['=== NATIVE VERSION STAMPER ===', f'Target: {target_path}']
    log_system(head, f'Starting version stamp on {target_path}')

    directory = os.path.dirname(os.path.abspath(target_path))
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            log.append(f'Created directory: {directory}')
        except PermissionError:
            log.append(
                f'Error: No permission to create the directory {directory}')
            return HANDLER_PERMISSIONS_ERROR_CODE, '\n'.join(log)
        except OSError as e:
            log.append(f'[ERROR] Could not create directory {directory}: {e}')
            return HANDLER_WRITE_ERROR_CODE, '\n'.join(log)

    data: Dict[str, Any] = dict()
    if os.path.exists(target_path):
        try:
            with open(target_path, 'r', encoding=_ENCODING) as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    log.append(
                        f'[WARNING] {target_path} is corrupt. Re-initializing.')
        except PermissionError:
            log.append(f'Error: No permission to read {target_path}')
            return HANDLER_PERMISSIONS_ERROR_CODE, '\n'.join(log)
        except OSError as e:
            log.append(
                f'[WARNING] Could not read {target_path}: {e}. Re-initializing.'
            )
            return HANDLER_INTERNAL_ERROR_CODE, '\n'.join(log)

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

    log.append(f'  > Hash:    {build_meta["Hash"]}')
    log.append(f'  > Date:    {build_meta["Date"]}')
    log.append(f'  > Builder: {build_meta["Builder"]}')

    if 'Game' not in data:
        data['Game'] = {
            'Name': _DEFAULT_GAME_NAME,
            'Major': 0,
            'Minor': 0,
            'Patch': 0,
            'Label': 'DEV',
        }

    if 'Target' not in data:
        data['Target'] = {'Environment': 'Production', 'Store': 'Steam'}

    try:
        with open(target_path, 'w', encoding=_ENCODING) as f:
            try:
                json.dump(data, f, indent=_DEFAULT_INDENT)
            except (TypeError, ValueError) as e:
                log.append(f'[ERROR] Failed to write to {target_path}: {e}')
                return HANDLER_WRITE_ERROR_CODE, '\n'.join(log)
    except FileNotFoundError:
        log.append('The directory path does not exist.')
        return HANDLER_FILE_NOT_FOUND_CODE, '\n'.join(log)
    except PermissionError:
        log.append('You do not have write permissions for this file.')
        return HANDLER_PERMISSIONS_ERROR_CODE, '\n'.join(log)
    except (IOError, OSError) as e:
        log.append(f'[ERROR] Version Stamp Failed: {str(e)}')
        return HANDLER_INTERNAL_ERROR_CODE, '\n'.join(log)

    log.append('[SUCCESS] Version Stamp Applied.')
    logging.info(f'[Success]: {"\n".join(log)}')
    return HANDLER_SUCCESS_CODE, '\n'.join(log)
