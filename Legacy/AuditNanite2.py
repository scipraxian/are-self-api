"""Unreal Engine script to audit shadow settings on non-Nanite meshes.

This script identifies static meshes with Nanite disabled that use translucent
materials set to cast ray-traced shadows, which can impact performance.
"""

import logging

import unreal

# Configure logging
logger = logging.getLogger(__name__)


def get_material_blend_mode(material_interface):
    """Safely retrieves the blend mode from a Material or Material Instance.

    Args:
        material_interface (unreal.MaterialInterface): The material to check.

    Returns:
        unreal.BlendMode or None: The blend mode of the base material.
    """
    if not material_interface:
        return None

    # Get the base material if it's an instance
    base_mat = material_interface
    if isinstance(material_interface, unreal.MaterialInstance):
        base_mat = material_interface.parent

        # Walk up the chain to find the real Material
        while isinstance(base_mat, unreal.MaterialInstance):
            base_mat = base_mat.parent

    if isinstance(base_mat, unreal.Material):
        return base_mat.blend_mode
    return None


def check_material_shadows(material_interface):
    """Checks if a material is set to cast ray traced shadows.

    Args:
        material_interface (unreal.MaterialInterface): The material to check.

    Returns:
        bool: True if 'cast_ray_traced_shadows' is enabled on the base material.
    """
    if not material_interface:
        return False

    # 1. Drill down to the Base Material
    base_mat = material_interface
    if isinstance(material_interface, unreal.MaterialInstance):
        base_mat = material_interface.parent
        while isinstance(base_mat, unreal.MaterialInstance):
            base_mat = base_mat.parent

    # 2. Check the property safely
    if isinstance(base_mat, unreal.Material):
        try:
            return base_mat.get_editor_property('cast_ray_traced_shadows')
        except Exception:  # pylint: disable=broad-except
            return False

    return False


def audit_nanite_shadows():
    """Audits non-Nanite meshes for shadow-casting translucent materials."""
    # --- CONFIGURATION ---
    search_root = '/Game/Bin'

    print('=' * 55)
    print(f'   NON-NANITE SHADOW AUDIT: {search_root}')
    print('   Target: Non-Nanite Meshes with Shadow-Casting Materials')
    print('=' * 55)

    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # Filter for Static Meshes
    asset_filter = unreal.ARFilter(
        package_paths=[search_root],
        recursive_paths=True,
        class_names=['StaticMesh'],
        include_only_on_disk_assets=True
    )

    assets = asset_registry.get_assets(asset_filter)

    offender_count = 0

    with unreal.ScopedSlowTask(len(assets), 'Hunting Shadows...') as task:
        task.make_dialog(True)

        for asset_data in assets:
            if task.should_cancel():
                break
            task.enter_progress_frame(1)

            # 1. Load Mesh
            mesh = asset_data.get_asset()
            if not mesh:
                continue

            # 2. Check Nanite (We only care if Nanite is OFF)
            try:
                nanite_settings = mesh.get_editor_property('nanite_settings')
                if nanite_settings.enabled:
                    continue  # Nanite is ON, skip it
            except Exception:  # pylint: disable=broad-except
                continue

            # 3. Check Materials
            # Opaque materials are fine, we look for translucent ones.
            num_materials = mesh.get_num_sections(0)  # LOD 0

            for i in range(num_materials):
                mat = mesh.get_material(i)
                if not mat:
                    continue

                blend_mode = get_material_blend_mode(mat)

                # We care about Translucent/Additive/Modulate
                if (blend_mode != unreal.BlendMode.BLEND_OPAQUE and
                        blend_mode != unreal.BlendMode.BLEND_MASKED):

                    casts_shadows = check_material_shadows(mat)

                    if casts_shadows:
                        logger.info('[OFFENDER] %s', asset_data.package_name)
                        logger.info('    > Material: %s', mat.get_name())
                        logger.info('    > Blend: %s', blend_mode)
                        logger.info('    > Cast RayTraced Shadows: TRUE')
                        offender_count += 1
                        # Break loop, report mesh once
                        break

    print('-' * 55)
    logger.info('Scan Complete.')
    logger.info(
        ' > Found %d Non-Nanite meshes with Shadow-Casting Translucency',
        offender_count
    )
    print('-' * 55)


if __name__ == '__main__':
    audit_nanite_shadows()