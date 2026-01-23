from hydra.models import HydraSpell


def spaces_have_quotes(string: str) -> str:
    """Assert strings with spaces have quotes around them."""
    if ' ' in string and '"' not in string:
        return f'"{string}"'
    return string


def spell_switches_and_arguments(spell_id: int) -> tuple[str, list[str]]:
    """Resolve the arguments and switches for the spell.

    returns: (str([ordered arguments] [switches]),
                  list[str]([ordered arguments] [switches]))

    TODO: resolve templates.
    """
    spell = HydraSpell.objects.get(id=spell_id)

    ordered_arguments_string = ''
    ordered_arguments_list = []

    for (
        assignment
    ) in spell.talos_executable.talosexecutableargumentassignment_set.all():
        item_string = spaces_have_quotes(assignment.argument.argument.strip())
        ordered_arguments_string += ' ' + item_string
        ordered_arguments_list.append(item_string)

    for assignment in spell.hydraspellargumentassignment_set.all():
        item_string = spaces_have_quotes(assignment.argument.argument.strip())
        ordered_arguments_string += ' ' + item_string
        ordered_arguments_list.append(item_string)

    ordered_arguments_string = ordered_arguments_string.strip()

    switch_string = ''
    switch_list = []

    for switch in spell.talos_executable.switches.all():
        item_string = spaces_have_quotes(switch.flag.strip())
        if switch.value:
            item_string += spaces_have_quotes(switch.value.strip())
        switch_string += ' ' + item_string
        switch_list.append(item_string)

    for switch in spell.switches.all():
        item_string = spaces_have_quotes(switch.flag.strip())
        if switch.value:
            item_string += spaces_have_quotes(switch.value.strip())
        switch_string += ' ' + item_string
        switch_list.append(item_string)

    switch_string = switch_string.strip()

    final_string = (ordered_arguments_string + ' ' + switch_string).strip()
    final_list = ordered_arguments_list + switch_list

    return final_string, final_list
