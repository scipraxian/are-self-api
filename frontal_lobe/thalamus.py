import asyncio
from typing import Optional

from asgiref.sync import sync_to_async

from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from prefrontal_cortex.models import PFCTask
from hippocampus.hippocampus import TalosHippocampus


async def relay_sensory_state(turn_record: ReasoningTurn) -> str:
    """
    The Thalamus.
    Compiles the current state of the world, active Agile tasks, and memories,
    relaying them as a single sensory payload to the Frontal Lobe.
    """
    session = turn_record.session
    current_turn = turn_record.turn_number

    # 1. Active Task (From the Agile Board, NOT ReasoningGoals)
    task_str = await _read_active_task(session)

    # 2. Hippocampus Catalog
    if current_turn == 1:
        catalog_block = await TalosHippocampus.get_turn_1_catalog(session.head)
    else:
        catalog_block = await TalosHippocampus.get_recent_catalog(session)

    # 3. Historical Log (River of 6)
    history_str = await _build_river_of_six(session, current_turn)

    # 4. Telemetry Header & Warnings
    header_str = await _build_telemetry_header(
        session, turn_record, len(history_str)
    )

    return (
        f'SESSION ID: {session.id}\n\n'
        f'{header_str}\n'
        f'[WAKING STATE: ACTIVE TASK]\n{task_str}\n\n'
        f'{catalog_block}'
        f'[HISTORICAL LOG (RIVER OF 6)]\n{history_str}\n'
        f'[YOUR MOVE]\n'
        f"Write your reasoning starting with 'THOUGHT: '. Stop writing text immediately after your thought and invoke your tools natively. DO NOT generate fake system diagnostics."
    )


async def _read_active_task(session: ReasoningSession) -> str:
    """Reads the assigned Task ID from the blackboard."""
    blackboard = session.head.blackboard or {}
    task_id = blackboard.get('active_pfc_task_id')

    if not task_id:
        return 'NO ACTIVE TASK ASSIGNED. You must query the Agile Board or consult the PM.'

    try:
        task = await sync_to_async(
            PFCTask.objects.select_related('story', 'story__epic').get
        )(id=task_id)

        return (
            f'EPIC: {task.story.epic.name}\n'
            f'STORY: {task.story.name}\n'
            f'TASK: {task.name}\n'
            f'DETAILS: {task.description}'
        )
    except PFCTask.DoesNotExist:
        return f'ERROR: Task ID {task_id} not found on the Agile Board.'


async def _build_river_of_six(
    session: ReasoningSession, current_turn: int
) -> str:
    """Compiles the recent historical log."""
    recent_turns = await sync_to_async(list)(
        session.turns.filter(
            status_id=ReasoningStatusID.COMPLETED,
        ).order_by('-turn_number')[:6]
    )
    recent_turns.reverse()

    if not recent_turns:
        return 'No recent internal monologue.\n'

    history_str = ''
    for t in recent_turns:
        t_len = len(t.thought_process) if t.thought_process else 0
        cap = session.current_level * 1000
        status = 'SUCCESS' if t_len <= cap else 'FAILED'

        history_str += f'--- CYCLE {t.turn_number} RETROSPECTIVE ---\n'
        history_str += f'* Footprint: {status} ({t_len}/{cap} chars)\n'
        history_str += (
            f'* Your Thought: {t.thought_process or "No internal monologue."}\n'
        )

        age = current_turn - t.turn_number
        tool_calls = await sync_to_async(list)(
            t.tool_calls.select_related('tool').all()
        )

        if not tool_calls:
            history_str += '* Tools Executed: None\n'

        for tc in tool_calls:
            history_str += f'* Tool Executed: {tc.tool.name}({tc.arguments})\n'
            if age <= 3:
                history_str += f'  - L1 Result: {tc.result_payload}\n'
                if age == 3:
                    history_str += f'  - System Warning: L1 EVICTION IMMINENT. FLUSH TO ENGRAMS.\n'
            else:
                history_str += f'  - L2 Result: [DATA EVICTED FROM L1 CACHE. REQUIRES ENGRAM RETRIEVAL.]\n'
        history_str += '\n'
    return history_str


async def _build_telemetry_header(
    session: ReasoningSession, turn_record: ReasoningTurn, l1_cache_size: int
) -> str:
    """Constructs the system diagnostics and biological warnings."""
    last_turn = turn_record.last_turn
    max_turns = session.max_turns
    current_turn = turn_record.turn_number
    remaining_turns = max_turns - current_turn
    target_capacity = session.current_level * 1000

    # Self-Derive Efficiency and Level Status
    last_output_len = 0
    efficiency_status = 'N/A'
    if last_turn and last_turn.thought_process:
        last_output_len = len(last_turn.thought_process)
        efficiency_status = (
            'OPTIMAL'
            if last_output_len <= target_capacity
            else 'INEFFICIENT (XP PENALTY)'
        )

    level_up_str = (
        ' | [LEVEL UP! Focus Pool Fully Restored]'
        if session.current_focus == session.max_focus and current_turn > 1
        else ''
    )

    milestone_kicks = ''
    if current_turn == max_turns // 2:
        milestone_kicks = (
            '\n[WARNING: 50% of allocated compute cycles expended.]'
        )
    elif remaining_turns == 10:
        milestone_kicks = (
            '\n[CRITICAL: 10 compute cycles remaining. Finalize diagnostics.]'
        )
    elif remaining_turns == 1:
        milestone_kicks = '\n[TERMINAL CYCLE. Submit final report via mcp_conclude_session or fail operation.]'

    latency_str = ''
    input_bandwidth = 0
    if last_turn:
        delta_t = (
            last_turn.inference_time.total_seconds()
            if last_turn.inference_time
            else 0
        )
        latency_str = f'\nDelta T (Previous Compute): {delta_t:.2f}s'
        if delta_t > 60.0:
            latency_str += (
                ' (WARNING: SYSTEM LAG DETECTED - REDUCE CONTEXT FOOTPRINT)'
            )

        tool_calls = await sync_to_async(list)(last_turn.tool_calls.all())
        for tc in tool_calls:
            input_bandwidth += len(tc.result_payload or '')

    input_bandwidth_str = (
        f'L1 Input Payload: {input_bandwidth} chars pulled.'
        if last_turn
        else 'L1 Input Payload: 0 chars pulled.'
    )

    pressure_warning = ''
    if l1_cache_size > 20000:
        pressure_warning = (
            '\n[CRITICAL WARNING: COGNITIVE OVERLOAD DETECTED]\n'
            f'Your recent memory buffer is massive ({l1_cache_size} characters). '
            'If you pull more data, you will suffer a fatal crash. '
            'You MUST use `mcp_pass` to rest and flush old data out of your L1 cache before proceeding.\n'
        )
    elif l1_cache_size > 12000:
        pressure_warning = (
            '\n[WARNING: CONTEXT PRESSURE RISING]\n'
            f'Your memory buffer is getting heavy ({l1_cache_size} characters). '
            'Consider saving your findings to Engrams and using `mcp_pass` to clear your cache.\n'
        )

    return (
        f'[SYSTEM DIAGNOSTICS]\n'
        f'[CYCLE {current_turn} / {max_turns}] | Speedrun Bounty: {remaining_turns * 1000} XP{milestone_kicks}\n'
        f'Level: {session.current_level} | XP: {session.total_xp} | Focus Pool: {session.current_focus} / {session.max_focus}{level_up_str}{latency_str}\n'
        f'Output Footprint (Prev Turn): {last_output_len} / {target_capacity} chars -> Efficiency Bonus: {efficiency_status}\n'
        f'{pressure_warning}'
        f'{input_bandwidth_str}\n'
    )
