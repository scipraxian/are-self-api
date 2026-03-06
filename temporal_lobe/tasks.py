import logging

from celery import shared_task

from central_nervous_system.central_nervous_system import CNS
from temporal_lobe.temporal_lobe import fetch_canonical_temporal_pathway

logger = logging.getLogger(__name__)

@shared_task
def autonomous_temporal_tick():
    """
    The Autonomous Heartbeat: Runs periodically via Celery Beat.
    Wakes up the Temporal Lobe to check the clock and dispatch pending workers.
    """
    try:
        pathway = fetch_canonical_temporal_pathway()
        cns = CNS(pathway_id=pathway.id)
        cns.start()
        logger.info(f"[HEARTBEAT] Temporal Metronome Fired: SpikeTrain {cns.spike_train.id}")
        return str(cns.spike_train.id)
    except Exception as e:
        logger.error(f"[HEARTBEAT] Failed to fire Temporal Lobe: {e}")
        return "Failed"
