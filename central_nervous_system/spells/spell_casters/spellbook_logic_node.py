import asyncio

from asgiref.sync import sync_to_async

from central_nervous_system.models import HydraHead
from central_nervous_system.utils import (
    get_active_environment,
    resolve_environment_context,
)


async def spellbook_logic_node(head_id: str) -> tuple[int, str]:
    """
    Executes flow control (Retry/Wait).
    Uses Provenance to count retries without needing state storage.
    """

    # 1. Fetch Head with Provenance
    head = await sync_to_async(lambda: HydraHead.objects.select_related(
        'spell', 'provenance').get(id=head_id))()

    # 2. Parse Arguments (retry=N, delay=N)

    env = await sync_to_async(get_active_environment)(head)
    full_context = await sync_to_async(resolve_environment_context)(
        head_id=head.id)

    full_cmd = await sync_to_async(head.spell.get_full_command
                                  )(environment=env, extra_context=full_context)

    # We only care about arguments, skipping the executable (index 0)
    cmd_list = full_cmd[1:]
    max_retries = 0
    delay_seconds = 0

    for arg in cmd_list:
        if arg.startswith('retry='):
            max_retries = int(arg.split('=')[1])
        elif arg.startswith('delay='):
            delay_seconds = int(arg.split('=')[1])

    # 3. Handle Delay (Holding the thread safely)
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    # 4. Handle Retry Logic via Provenance Walking
    if max_retries > 0:
        current_retry_count = 0

        # We walk back up the family tree
        cursor = head.provenance
        while cursor:
            # FIX: Check the GRAPH LOCATION (Node ID), not the Spell ID
            if cursor.node_id == head.node_id:
                current_retry_count += 1
            cursor = await sync_to_async(lambda: cursor.provenance)()

        log_msg = (f'Retry Check: '
                   f'Attempt {current_retry_count + 1} of {max_retries + 1}')

        if current_retry_count < max_retries:
            # We are under the limit -> Return SUCCESS (Green Wire loops back)
            return 200, f'{log_msg} -> LOOPING'
        else:
            # Limit hit -> Return FAILURE (Red Wire goes to error handler)
            return 500, f'{log_msg} -> LIMIT REACHED'

    return 200, 'Logic Node Pass-Through'
