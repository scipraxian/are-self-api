"""Unreal Engine script to audit actors based on Data Layer assignments.

This script searches for loaded actors in the current level that are assigned
to a specific data layer and selects them in the editor.
"""

import logging

import unreal

# Configure logging
logger = logging.getLogger(__name__)


def audit_layer(layer_name_substring):
    """Searches for actors assigned to a data layer and selects them.

    Args:
        layer_name_substring (str): The substring to search for in data layer
            asset names.
    """
    logger.info(
        "--- AUDIT: Searching for Data Layer containing '%s' ---",
        layer_name_substring
    )

    # Note: In World Partition, this only gets *loaded* actors.
    # Ensure relevant cells/layers are loaded first!
    all_actors = unreal.EditorLevelLibrary.get_all_level_actors()

    count = 0
    found_actors = []

    with unreal.ScopedSlowTask(
        len(all_actors), 'Auditing Data Layers...'
    ) as slow_task:
        slow_task.make_dialog(True)

        for actor in all_actors:
            if slow_task.should_cancel():
                break
            slow_task.enter_progress_frame(1)

            # In UE 5.1+, Data Layers are assigned via 'data_layer_assets'
            layers = actor.get_editor_property('data_layer_assets')

            if layers:
                for layer in layers:
                    # layer is a DataLayerAsset object
                    layer_name = layer.get_name()

                    if layer_name_substring.lower() in layer_name.lower():
                        actor_label = actor.get_actor_label()
                        actor_class = actor.get_class().get_name()
                        logger.info(
                            '[FOUND] Actor: %s (%s) -> Layer: %s',
                            actor_label, actor_class, layer_name
                        )
                        found_actors.append(actor)
                        count += 1
                        break

    print('---------------------------------------------------')
    logger.info(
        'Total Actors on Layer \'%s\': %d', layer_name_substring, count
    )

    if count > 0:
        logger.info('Selecting found actors...')
        unreal.EditorLevelLibrary.set_selected_level_actors(found_actors)


# --- RUN CONFIGURATION ---
SEARCH_TERM = 'DL_Hotel_Zygnus'

if __name__ == '__main__':
    audit_layer(SEARCH_TERM)
