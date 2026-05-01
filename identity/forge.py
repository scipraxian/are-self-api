import logging

from django.db import transaction

from identity.models import Identity, IdentityDisc

logger = logging.getLogger(__name__)


@transaction.atomic
def forge_identity_disc(
    base_identity: Identity, custom_name: str = None
) -> IdentityDisc:
    """
    RTS Mechanic: Stamps a brand new Level 1 IdentityDisc from this Base Identity.
    Used when a user drags a Base Identity directly onto a Live Shift.
    """
    new_name = custom_name if custom_name else f'{base_identity.name} [Program]'

    counter = 0
    while IdentityDisc.objects.filter(name=new_name).exists():
        counter += 1
        new_name = f'{new_name} [Mk. {counter}]'

    # 1. Create the Disc with the standard (Direct/ForeignKey) fields
    new_disc = IdentityDisc.objects.create(
        name=new_name,
        identity_type=base_identity.identity_type,
        system_prompt_template=base_identity.system_prompt_template,
        category=base_identity.category,
        selection_filter=base_identity.selection_filter,
        avatar=base_identity.avatar,
        level=1,
        xp=0,
        available=True,
        successes=0,
        failures=0,
        timeouts=0,
    )

    # 2. Copy the Many-to-Many relationships
    new_disc.tags.set(base_identity.tags.all())
    new_disc.addons.set(base_identity.addons.all())
    new_disc.enabled_tools.set(base_identity.enabled_tools.all())

    logger.info(f'Created new IdentityDisc: {new_disc.name}')

    return new_disc
