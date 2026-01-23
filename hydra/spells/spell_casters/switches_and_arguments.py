from hydra.models import HydraSpell


def spell_switches_and_arguments(spell_id: int) -> list[str]:
    """Resolve the arguments and switches for the spell.

    returns: list[str]([ordered arguments] [switches])
    """
    spell = HydraSpell.objects.get(id=spell_id)

    ordered_arguments_list = []

    # 1. Process Arguments
    all_assignments = list(
        spell.talos_executable.talosexecutableargumentassignment_set.all()
    ) + list(spell.hydraspellargumentassignment_set.all())

    for assignment in all_assignments:
        raw_arg = assignment.argument.argument.strip()
        # Execution List: Raw string (subprocess handles quoting)
        ordered_arguments_list.append(raw_arg)

    switch_list = []

    # 2. Process Switches
    all_switches = list(spell.talos_executable.switches.all()) + list(
        spell.switches.all()
    )

    for switch in all_switches:
        flag = switch.flag.strip()
        value = switch.value.strip() if switch.value else ''

        # Execution List Construction
        # We append the flag+value as one item, RAW (no added quotes)
        # Python's subprocess will handle wrapping this safely.
        exec_item = flag + value
        switch_list.append(exec_item)

    final_list = ordered_arguments_list + switch_list

    return final_list
