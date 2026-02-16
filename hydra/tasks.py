import logging

from celery import shared_task
from django.db import transaction

from .models import HydraHead, HydraHeadStatus
from .spells.spell_casters.generic_spell_caster import GenericSpellCaster

logger = logging.getLogger(__name__)


@shared_task
def check_next_wave(spawn_id):
    """
    Checks the status of a spawn and triggers the next batch of heads if ready.
    """
    from .hydra import Hydra

    logger.info(f'[CELERY] Checking next wave for Spawn {spawn_id}')
    try:
        controller = Hydra(spawn_id=spawn_id)
        # Accessing internal dispatch logic directly for task efficiency
        controller.dispatch_next_wave()
    except Exception as e:
        logger.exception(
            f'[CELERY] Check Wave Failed for Spawn {spawn_id}: {e}'
        )
        raise


@shared_task(bind=True)
def cast_hydra_spell(self, head_id):
    """
    The Main Execution Task.
    Instantiates the GenericSpellCaster to run the pipeline.
    """
    logger.info(f'Task starting for Head ID: {head_id}')

    # Store spawn_id for the finally block
    spawn_id = None

    try:
        # 0. Pre-fetch spawn_id so we can drive the engine even if the Caster explodes
        try:
            head = HydraHead.objects.only('spawn_id').get(id=head_id)
            spawn_id = head.spawn_id
            head.celery_task_id = self.request.id
            head.save(update_fields=['celery_task_id'])
        except HydraHead.DoesNotExist:
            logger.error(f'Head {head_id} missing during cast!')
            return

        # 1. Instantiate the Caster
        caster = GenericSpellCaster(head_id=head_id)

        # 2. Run the Logic (Loads DB -> runs Async Pipeline)
        caster.execute()

        logger.info(f'Task completed successfully for Head ID: {head_id}')

    except Exception as e:
        logger.exception(f'GenericSpellCaster crashed for Head ID {head_id}')

        # Emergency DB Update to prevent "Pending Forever" state
        try:
            head = HydraHead.objects.get(id=head_id)
            head.status_id = HydraHeadStatus.FAILED
            head.execution_log += f'\n[CELERY FATAL] Task crashed: {e}\n'
            head.save(update_fields=['status', 'execution_log'])
        except Exception:
            pass

        raise e

    finally:
        # 3. SELF-DRIVING ENGINE: Trigger the next wave automatically
        if spawn_id:
            logger.info(
                f'[CELERY] Spell finished. Triggering next wave for Spawn {spawn_id}'
            )
            # Use on_commit if in a transaction, otherwise call immediately
            transaction.on_commit(lambda: check_next_wave.delay(spawn_id))
