from hydra.models import HydraSpell


def spell_switches_and_arguments(spell_id: int) -> str:
    """Resolve the arguments and switches for the spell.

    returns: str([ordered arguments] [switches]).strip()

    TODO: resolve templates.
    """
    spell = HydraSpell.objects.get(id=spell_id)

    ordered_arguments_string = ''

    for assignment in spell.talos_executable.talosexecutableargumentassignment_set.all():
        ordered_arguments_string += ' ' + assignment.argument.argument

    for assignment in spell.hydraspellargumentassignment_set.all():
        ordered_arguments_string += ' ' + assignment.argument.argument

    ordered_arguments_string = ordered_arguments_string.strip()

    switch_string = ''

    for switch in spell.talos_executable.switches.all():
        switch_string += ' ' + switch.flag
        if switch.value:
            switch_string += switch.value

    for switch in spell.switches.all():
        switch_string += ' ' + switch.flag
        if switch.value:
            switch_string += switch.value

    switch_string = switch_string.strip()

    final_string = (ordered_arguments_string + ' ' + switch_string).strip()
    return final_string
