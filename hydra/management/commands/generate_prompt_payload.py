import logging
import os
import tempfile

from django.core.management.base import BaseCommand

from environments.variable_renderer import VariableRenderer
from hydra.models import HydraHead
from hydra.utils import resolve_environment_context

logger = logging.getLogger(__name__)


BLACKBOARD_FIELD_NAME = 'blackboard'
BLACKBOARD_RESULT_KEY = 'local_prompt_path'
DEFAULT_TARGET_KEY = 'prompt'
HEAD_ARGUMENT = '--head_id'
HEAD_ID = 'head_id'
KEY = 'key'
KEY_ARGUMENT = '--key'
TEMP_FILE_PREFIX = 'talos_payload_'
TEMP_FILE_SUFFIX = '.txt'


class Command(BaseCommand):
    help = (
        'Renders a prompt and saves it to a temp file for remote AI execution.'
    )

    def add_arguments(self, parser):
        parser.add_argument(HEAD_ARGUMENT, type=str, required=True)
        parser.add_argument(KEY_ARGUMENT, type=str, default=DEFAULT_TARGET_KEY)

    def handle(self, *args, **options):
        head_id = options[HEAD_ID]
        target_key = options[KEY]
        try:
            head = HydraHead.objects.get(id=head_id)
        except HydraHead.DoesNotExist:
            logger.error(f'Error: Head {head_id} not found.')
            return
        head_context = resolve_environment_context(head_id=head.id)
        raw_template = head_context.get(target_key, '')
        if not raw_template:
            logger.warning(
                f"Key '{target_key}' was empty or not found in context."
            )
        rendered_payload = VariableRenderer.render_string(
            raw_template, head_context
        )

        logger.info(f'Payload generated [{len(rendered_payload)} chars]')

        fd, temp_path = tempfile.mkstemp(
            prefix=TEMP_FILE_PREFIX, suffix=TEMP_FILE_SUFFIX
        )

        logger.info(f'Temp File Created {temp_path}')

        with os.fdopen(fd, 'w', encoding='utf-8', errors='replace') as f:
            f.write(rendered_payload)

        logger.info(f'::blackboard_set {BLACKBOARD_RESULT_KEY}::{temp_path}')
        logger.info('generate_prompt_payload Command Complete.')
