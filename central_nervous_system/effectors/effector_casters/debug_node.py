import logging
import uuid

from asgiref.sync import sync_to_async

from central_nervous_system.models import NeuronContext, Spike

logger = logging.getLogger(__name__)


async def debug_node(spike_id: uuid.UUID) -> tuple[int, str]:
    """
    Debug Node — logs blackboard state and neuron context to the worker log.

    Drop this into any pathway to get visibility at that point in the graph.
    Reads NeuronContext for a custom `debug_label` key (defaults to 'DEBUG').
    Always returns 200 (success) so the graph continues.
    """
    spike = await sync_to_async(
        Spike.objects.select_related('neuron', 'effector', 'spike_train').get
    )(id=spike_id)

    label = 'DEBUG'
    if spike.neuron:
        ctx = await sync_to_async(list)(
            NeuronContext.objects.filter(neuron=spike.neuron)
        )
        ctx_dict = {c.key: c.value for c in ctx}
        label = ctx_dict.get('debug_label', label)
    else:
        ctx_dict = {}

    bb_keys = list(spike.blackboard.keys()) if spike.blackboard else []

    logger.info(
        '[DEBUG NODE] <%s> Spike %s | Train %s | Neuron %s | '
        'Blackboard keys: %s | Context: %s',
        label,
        spike.id,
        spike.spike_train_id,
        spike.neuron_id or 'N/A',
        bb_keys,
        ctx_dict,
    )

    if spike.blackboard:
        for key, value in spike.blackboard.items():
            preview = str(value)[:200]
            logger.info('[DEBUG NODE] <%s>   BB[%s] = %s', label, key, preview)

    output = f'[{label}] Blackboard: {bb_keys} | Context: {list(ctx_dict.keys())}'
    return 200, output
