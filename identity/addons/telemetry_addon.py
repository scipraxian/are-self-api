from typing import List

from django.db.models import Sum
from django.db.models.functions import Length

from frontal_lobe.models import ChatMessage, ChatMessageRole, ReasoningTurn
from identity.addons.addon_package import AddonPackage


def telemetry_addon(package: AddonPackage) -> List[ChatMessage]:
    """
    Identity Addon (Phase: CONTEXT)
    Constructs system diagnostics, latency reports, and cognitive load warnings.
    """
    if not package.reasoning_turn_id or not package.session_id:
        return []

    turn_record = ReasoningTurn.objects.select_related(
        'last_turn', 'session'
    ).get(id=package.reasoning_turn_id)
    session = turn_record.session
    last_turn = turn_record.last_turn

    current_turn = package.turn_number
    max_turns = session.max_turns
    remaining_turns = max_turns - current_turn
    target_capacity = session.current_level * 1000

    # 1. Self-Derive Efficiency and Level Status
    last_output_len = 0
    efficiency_status = 'N/A'
    if last_turn and last_turn.thought_process:
        last_output_len = len(last_turn.thought_process)
        efficiency_status = (
            'OPTIMAL'
            if last_output_len <= target_capacity
            else 'INEFFICIENT (XP PENALTY)'
        )

    # 2. Calculate Latency & Bandwidth
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

        # Sum up the payload sizes of the tools fired last turn
        for tc in last_turn.tool_calls.all():
            input_bandwidth += len(tc.result_payload or '')

    input_bandwidth_str = f'L1 Input Payload: {input_bandwidth} chars pulled.'

    # 3. Calculate Cognitive Load (L1 Cache Size)
    # Estimate the size of the active memory window (last 6 turns)
    cutoff_turn = max(1, current_turn - 6)
    l1_cache_agg = ChatMessage.objects.filter(
        session_id=package.session_id,
        turn__turn_number__gte=cutoff_turn,
        is_volatile=False,
    ).aggregate(total_chars=Sum(Length('content')))

    l1_cache_size = l1_cache_agg.get('total_chars') or 0

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

    # 4. Build Final String
    diagnostics = (
        f'[SYSTEM DIAGNOSTICS]\n'
        f'[CYCLE {current_turn} / {max_turns}] | Speedrun Bounty: {remaining_turns * 1000} XP\n'
        f'Output Footprint (Prev Turn): {last_output_len} / {target_capacity} chars -> Efficiency Bonus: {efficiency_status}\n'
        f'Time Efficiency (Prev Turn): {latency_str}'
        f'{pressure_warning}'
        f'\n{input_bandwidth_str}\n'
    )

    return [
        ChatMessage(
            session_id=package.session_id,
            turn_id=package.reasoning_turn_id,
            role_id=ChatMessageRole.USER,
            content=diagnostics,
            is_volatile=True,
        )
    ]
