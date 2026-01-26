import logging

from celery import shared_task

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

    try:
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
            # DB might be unreachable; nothing more we can do
            pass

        raise e
