import logging

from celery import shared_task
from django.db import transaction

from .models import Spike, SpikeStatus

logger = logging.getLogger(__name__)


@shared_task
def check_next_wave(spike_train_id):
    """
    Checks the status of a spike_train and triggers the next batch of spikes if ready.
    """
    from .central_nervous_system import CNS  # circular import

    logger.debug(f'[CNS] Checking next wave for SpikeTrain {spike_train_id}')
    try:
        controller = CNS(spike_train_id=spike_train_id)
        # Accessing internal dispatch logic directly for task efficiency
        controller.dispatch_next_wave()
    except Exception as e:
        logger.exception(
            f'[CNS] Check Wave Failed for SpikeTrain {spike_train_id}: {e}'
        )
        raise


@shared_task(bind=True)
def fire_spike(self, spike_id):
    """
    The Main Execution Task.
    """
    logger.debug(f'Task starting for Spike ID: {spike_id}')

    # Store spike_train_id for the finally block
    spike_train_id = None

    try:
        # 0. Pre-fetch spike_train_id so we can drive the engine even if the Caster explodes
        try:
            spike = Spike.objects.only('spike_train_id').get(id=spike_id)
            spike_train_id = spike.spike_train_id
            spike.celery_task_id = self.request.id
            spike.save(update_fields=['celery_task_id'])
        except Spike.DoesNotExist:
            logger.error(f'Spike {spike_id} missing during cast!')
            return

        # 1. Instantiate the Caster (forced local)
        from .effectors.effector_casters.neuromuscular_junction import (
            NeuroMuscularJunction,
        )

        caster = NeuroMuscularJunction(spike_id=spike_id)

        # 2. Run the Logic (Loads DB -> runs Async Pipeline)
        caster.execute()

        logger.debug(f'Task completed successfully for Spike ID: {spike_id}')

    except Exception as e:
        logger.exception(
            f'NeuroMuscularJunction crashed for Spike ID {spike_id}'
        )

        # Emergency DB Update to prevent "Pending Forever" state
        try:
            spike = Spike.objects.get(id=spike_id)
            spike.status_id = SpikeStatus.FAILED
            spike.execution_log += f'\n[CELERY FATAL] Task crashed: {e}\n'
            spike.save(update_fields=['status', 'execution_log'])
        except Exception:
            pass

        raise e

    finally:
        # 3. SELF-DRIVING ENGINE: Trigger the next wave automatically
        if spike_train_id:
            logger.debug(
                f'[CNS] Effector finished. Triggering next wave for SpikeTrain {spike_train_id}'
            )
            # Use on_commit if in a transaction, otherwise call immediately
            transaction.on_commit(lambda: check_next_wave.delay(spike_train_id))
