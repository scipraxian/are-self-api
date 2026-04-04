import asyncio
import logging

from asgiref.sync import sync_to_async

from central_nervous_system.models import Spike
from central_nervous_system.utils import resolve_environment_context  # NeuronContext is highest precedence

logger = logging.getLogger(__name__)

# ── NeuronContext key constants ──────────────────────────────
# These MUST match the keys used in the frontend node editors
# (RetryNeuronNode, GateNeuronNode, DelayNeuronNode) and in
# nodeConstants.ts EFFECTOR_DEFAULTS.
CTX_LOGIC_MODE = 'logic_mode'
CTX_MAX_RETRIES = 'max_retries'
CTX_DELAY = 'delay'
CTX_RETRY_DELAY = 'retry_delay'
CTX_GATE_KEY = 'gate_key'
CTX_GATE_OPERATOR = 'gate_operator'
CTX_GATE_VALUE = 'gate_value'

# Logic node modes — stored in NeuronContext as logic_mode=<value>.
MODE_RETRY = 'retry'
MODE_GATE = 'gate'
MODE_WAIT = 'wait'

# Gate operators for MODE_GATE.
OP_EXISTS = 'exists'
OP_EQUALS = 'equals'
OP_NOT_EQUALS = 'not_equals'
OP_GT = 'gt'
OP_LT = 'lt'

# Blackboard key written by retry mode.
BB_LOOP_COUNT = 'loop_count'


async def pathway_logic_node(spike_id: str) -> tuple[int, str]:
    """CNS Logic Node — flow control via blackboard state.

    Configuration lives in NeuronContext (per-node, set in graph editor):
        logic_mode:    retry | gate | wait  (default: retry for backwards compat)
        max_retries:   int  (retry mode — max loop iterations)
        delay:         int  (retry/wait modes — seconds to sleep)
        gate_key:      str  (gate mode — blackboard key to check)
        gate_operator: exists | equals | not_equals | gt | lt  (gate mode)
        gate_value:    str  (gate mode — expected value)

    Returns (200, msg) for SUCCESS axon, (500, msg) for FAILURE axon.
    """
    spike = await sync_to_async(
        lambda: Spike.objects.select_related(
            'effector', 'neuron'
        ).get(id=spike_id)
    )()

    # Resolve full context — NeuronContext values are highest precedence.
    context = await sync_to_async(resolve_environment_context)(
        spike_id=spike.id
    )

    mode = str(context.get(CTX_LOGIC_MODE, MODE_RETRY)).strip().lower()

    logger.info(
        '[LogicNode] Spike %s | mode=%s | neuron=%s | bb_keys=%s',
        spike_id, mode,
        spike.neuron_id if spike.neuron else 'N/A',
        list((spike.blackboard or {}).keys()),
    )

    if mode == MODE_RETRY:
        return await _handle_retry(spike, context)
    elif mode == MODE_GATE:
        return _handle_gate(spike, context)
    elif mode == MODE_WAIT:
        return await _handle_wait(context)
    else:
        logger.warning(
            '[LogicNode] Unknown mode "%s" on spike %s. Pass-through.',
            mode, spike_id,
        )
        return 200, f'Logic Node: unknown mode "{mode}", pass-through.'


async def _handle_retry(spike: Spike, context: dict) -> tuple[int, str]:
    """Walk provenance chain, count visits to this neuron, write loop_count."""
    max_retries = _safe_int(context.get(CTX_MAX_RETRIES, 0))
    delay = _safe_int(context.get(CTX_RETRY_DELAY, 0))

    if delay > 0:
        await asyncio.sleep(delay)

    if max_retries <= 0:
        logger.warning(
            '[LogicNode] Retry pass-through: max_retries=%s '
            '(raw=%r). Check NeuronContext for neuron %s.',
            max_retries,
            context.get(CTX_MAX_RETRIES),
            spike.neuron_id,
        )
        return 200, 'Retry mode: max_retries=0, pass-through.'

    # Read loop count from blackboard — starts at 0, increments each pass.
    # No provenance walking needed. The blackboard carries forward.
    bb = spike.blackboard or {}
    current_count = _safe_int(bb.get(BB_LOOP_COUNT, 0))

    log_msg = (
        f'Retry: attempt {current_count + 1} of {max_retries + 1}'
        f' (loop_count={current_count}, max_retries={max_retries})'
    )

    if current_count < max_retries:
        # Increment and write back for the next iteration.
        spike.blackboard[BB_LOOP_COUNT] = current_count + 1
        await sync_to_async(spike.save)(update_fields=['blackboard'])
        logger.info('[LogicNode] %s -> LOOPING', log_msg)
        return 200, f'{log_msg} -> LOOPING'
    else:
        logger.info('[LogicNode] %s -> LIMIT REACHED', log_msg)
        return 500, f'{log_msg} -> LIMIT REACHED'


def _handle_gate(spike: Spike, context: dict) -> tuple[int, str]:
    """Check a blackboard key against a condition."""
    gate_key = str(context.get(CTX_GATE_KEY, '')).strip()
    operator = str(context.get(CTX_GATE_OPERATOR, OP_EXISTS)).strip().lower()
    gate_value = str(context.get(CTX_GATE_VALUE, '')).strip()

    if not gate_key:
        return 500, 'Gate mode: no gate_key configured.'

    bb = spike.blackboard or {}
    bb_raw = bb.get(gate_key)
    key_exists = bb_raw is not None

    if operator == OP_EXISTS:
        if key_exists:
            return 200, f'Gate: "{gate_key}" exists -> PASS'
        return 500, f'Gate: "{gate_key}" not found -> FAIL'

    if not key_exists:
        return 500, f'Gate: "{gate_key}" not found, cannot evaluate {operator}.'

    bb_value = str(bb_raw).strip()

    if operator == OP_EQUALS:
        if bb_value == gate_value:
            return 200, f'Gate: "{gate_key}"="{bb_value}" == "{gate_value}" -> PASS'
        return 500, f'Gate: "{gate_key}"="{bb_value}" != "{gate_value}" -> FAIL'

    if operator == OP_NOT_EQUALS:
        if bb_value != gate_value:
            return 200, f'Gate: "{gate_key}"="{bb_value}" != "{gate_value}" -> PASS'
        return 500, f'Gate: "{gate_key}"="{bb_value}" == "{gate_value}" -> FAIL'

    if operator == OP_GT:
        if _safe_float(bb_value) > _safe_float(gate_value):
            return 200, f'Gate: "{gate_key}"={bb_value} > {gate_value} -> PASS'
        return 500, f'Gate: "{gate_key}"={bb_value} <= {gate_value} -> FAIL'

    if operator == OP_LT:
        if _safe_float(bb_value) < _safe_float(gate_value):
            return 200, f'Gate: "{gate_key}"={bb_value} < {gate_value} -> PASS'
        return 500, f'Gate: "{gate_key}"={bb_value} >= {gate_value} -> FAIL'

    return 500, f'Gate: unknown operator "{operator}".'


async def _handle_wait(context: dict) -> tuple[int, str]:
    """Pure delay. Always passes."""
    delay = _safe_int(context.get(CTX_DELAY, 0))
    if delay > 0:
        await asyncio.sleep(delay)
        return 200, f'Wait: delayed {delay}s -> PASS'
    return 200, 'Wait: no delay configured, pass-through.'


def _safe_int(value) -> int:
    """Parse an int from any value without raising."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _safe_float(value) -> float:
    """Parse a float from any value without raising."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
