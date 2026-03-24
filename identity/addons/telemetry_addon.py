import json
from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn


def telemetry_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: CONTEXT)
    Constructs system diagnostics, latency reports, and cognitive load warnings.
    """
    if not turn or not turn.session:
        return []

    session = turn.session
    last_turn = turn.last_turn
    current_turn = turn.turn_number

    max_turns = session.max_turns
    remaining_turns = max_turns - current_turn
    target_capacity = session.current_level * 1000

    last_output_len = 0
    efficiency_status = 'N/A'
    if (
        last_turn
        and last_turn.model_usage_record
        and last_turn.model_usage_record.response_payload
    ):
        last_output_len = len(
            str(last_turn.model_usage_record.response_payload)
        )
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

    input_bandwidth_str = f'L1 Input Payload: {input_bandwidth} chars pulled.'

    cutoff_turn = max(1, current_turn - 6)

    recent_turns = list(
        ReasoningTurn.objects.filter(
            session_id=session.id,
            turn_number__gte=cutoff_turn,
            turn_number__lt=current_turn,
            model_usage_record__isnull=False,
        ).select_related('model_usage_record')
    )

    l1_cache_size = 0
    for t in recent_turns:
        l1_cache_size += (
            len(json.dumps(t.model_usage_record.request_payload))
            if t.model_usage_record.request_payload
            else 0
        )
        l1_cache_size += (
            len(json.dumps(t.model_usage_record.response_payload))
            if t.model_usage_record.response_payload
            else 0
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

    diagnostics = (
        f'[SYSTEM DIAGNOSTICS]\n'
        f'[CYCLE {current_turn} / {max_turns}] | Speedrun Bounty: {remaining_turns * 1000} XP\n'
        f'Output Footprint (Prev Turn): {last_output_len} / {target_capacity} chars -> Efficiency Bonus: {efficiency_status}\n'
        f'Time Efficiency (Prev Turn): {latency_str}'
        f'{pressure_warning}'
        f'\n{input_bandwidth_str}\n'
    )

    return [{'role': 'system', 'content': diagnostics}]
