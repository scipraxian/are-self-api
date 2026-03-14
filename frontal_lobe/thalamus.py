import asyncio
from typing import Optional

from asgiref.sync import sync_to_async

from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from hippocampus.hippocampus import TalosHippocampus
from prefrontal_cortex.models import PFCTask


# TODO: push this upstream.
async def relay_sensory_state(turn_record: ReasoningTurn) -> str:
    """
    The Thalamus.
    Compiles the current state of the world, active Agile tasks, and memories
    for the *current* turn, and returns the final sensory trigger message.
    """
    session = turn_record.session
    current_turn = turn_record.turn_number

    # Hippocampus Catalog for this turn
    if current_turn == 1:
        catalog_block = await TalosHippocampus.get_turn_1_catalog(session.spike)
    else:
        catalog_block = await TalosHippocampus.get_recent_catalog(session)

    return (
        f'{catalog_block}\n\n'
        'YOUR MOVE:'
        "1. You MUST write your new and unique reasoning starting with 'THOUGHT: '.\n\n"
        '2. Stop writing text immediately after your thought.\n\n'
        '3. Invoke any required tool(s) natively.\n\n'
    )


# LEGACY
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


# TODO: This is good. we should add this back in in some way.
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
        f'[CYCLE {current_turn} / {max_turns}] | Speedrun Bounty: {remaining_turns * 1000} XP\n'
        f'Output Footprint (Prev Turn): {last_output_len} / {target_capacity} chars -> Efficiency Bonus: {efficiency_status}\n'
        f'Time Efficiency (Prev Turn): {latency_str}'
        f'{pressure_warning}'
        f'{input_bandwidth_str}\n'
    )
