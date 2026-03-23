import logging
from typing import Optional

from django.template import Context, Template
from django.template.exceptions import TemplateSyntaxError

from frontal_lobe.models import ReasoningTurn
from identity.models import IdentityDisc
from temporal_lobe.models import Iteration

logger = logging.getLogger(__name__)


def render_base_identity(
    identity_disc: Optional['IdentityDisc'] = None,
    iteration_id: Optional[int] = None,
    turn_number: int = 1,
    reasoning_turn_id: Optional[int] = None,
) -> str:
    """
    Compiles the immutable system laws for the current IdentityDisc using
    Django's native template engine. Looks up related ORM objects via IDs
    to provide full graph access to the template.
    """
    if not identity_disc:
        return 'No Identity mounted. Operating with blank slate.'

    raw_template = identity_disc.system_prompt_template or ''

    # Hydrate the ORM objects based on the incoming IDs
    reasoning_turn = None
    if reasoning_turn_id:
        reasoning_turn = (
            ReasoningTurn.objects.select_related('session', 'session__spike')
            .filter(id=reasoning_turn_id)
            .first()
        )

    iteration = None
    if iteration_id:
        iteration = Iteration.objects.filter(id=iteration_id).first()

    try:
        django_template = Template(raw_template)

        # Inject both the raw IDs and the hydrated objects
        context = Context(
            {
                'identity_disc': identity_disc,
                'iteration_id': iteration_id,
                'turn_number': turn_number,
                'reasoning_turn_id': reasoning_turn_id,
                'iteration': iteration,
                'reasoning_turn': reasoning_turn,
            }
        )
        rendered_prompt = django_template.render(context)
    except TemplateSyntaxError as e:
        logger.error(
            f'Template syntax error in IdentityDisc {identity_disc.id}: {e}'
        )
        rendered_prompt = raw_template
    except Exception as e:
        logger.error(
            f'Failed to render template for IdentityDisc {identity_disc.id}: {e}'
        )
        rendered_prompt = raw_template

    prompt_blocks = [rendered_prompt]
    prompt_blocks.append(f'Identity Disc: {identity_disc.name}')

    return '\n\n'.join(block for block in prompt_blocks if block.strip())


def build_identity_prompt(
    identity_disc: Optional['IdentityDisc'],
    iteration_id: Optional[int] = None,
    turn_number: int = 1,
    reasoning_turn_id: Optional[int] = None,
) -> str:
    """
    Dynamically compiles the system prompt based on the mounted IdentityDisc.
    Called by the Frontal Lobe via the Identity Info Addon.
    """
    if not identity_disc:
        return 'No Identity mounted. Operating with blank slate.'

    prompt_blocks = [
        render_base_identity(
            identity_disc=identity_disc,
            iteration_id=iteration_id,
            turn_number=turn_number,
            reasoning_turn_id=reasoning_turn_id,
        )
    ]

    if turn_number == 1 and identity_disc.last_message_to_self:
        prompt_blocks.append(
            f'### Message from previous instance ###\n'
            f'"{identity_disc.last_message_to_self}"'
        )

    return '\n\n'.join(prompt_blocks)
