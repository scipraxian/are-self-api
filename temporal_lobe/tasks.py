import logging

from celery import shared_task

from temporal_lobe.temporal_lobe import trigger_temporal_metronomes

logger = logging.getLogger(__name__)


@shared_task
def autonomous_temporal_tick():
    try:
        spawned_ids = trigger_temporal_metronomes()
        if not spawned_ids:
            return 'Skipped - No Active Iterations'
        return f'Success - Fired {len(spawned_ids)} Temporal Lobes'
    except Exception as e:
        logger.error(f'[HEARTBEAT] Failed: {e}')
        return f'Failed - {str(e)}'
