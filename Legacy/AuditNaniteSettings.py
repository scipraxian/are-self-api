"""Unreal Engine script to audit Nanite settings on static meshes.

This script scans a specified directory for static meshes with Nanite disabled,
filtering out items that match predefined ignore terms (e.g., glass).
"""

import logging

import unreal

# Configure logging
logger = logging.getLogger(__name__)


def audit_nanite_settings():
    """Audits meshes for disabled Nanite settings in a target folder."""
    # --- CONFIGURATION ---
    # Target folder (Recursive)
    search_root = '/Game/Bin'
    # Search terms to ignore (case insensitive)
    ignore_terms = ['glass', 'window', 'translucent']

    print('=' * 55)
    print(f'   NANITE AUDIT: {search_root}')
    print(f'   (Ignoring items containing: {ignore_terms})')
    print('=' * 55)

    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # Filter for Static Meshes only
    asset_filter = unreal.ARFilter(
        package_paths=[search_root],
        recursive_paths=True,
        class_names=['StaticMesh'],
        include_only_on_disk_assets=True
    )

    assets = asset_registry.get_assets(asset_filter)

    found_count = 0
    ignored_count = 0

    # Use a SlowTask so we don't freeze the editor while loading meshes
    with unreal.ScopedSlowTask(len(assets), 'Auditing Nanite...') as task:
        task.make_dialog(True)

        for asset_data in assets:
            if task.should_cancel():
                break
            task.enter_progress_frame(1)

            # Load the mesh to check settings
            mesh = asset_data.get_asset()
            if not mesh:
                continue

            # CHECK 1: Safe Access for Nanite Settings
            try:
                nanite_settings = mesh.get_editor_property('nanite_settings')
                is_nanite_enabled = nanite_settings.enabled
            except Exception:  # pylint: disable=broad-except
                logger.warning(
                    '[WARN] Could not read nanite_settings for %s',
                    asset_data.package_name
                )
                continue

            if not is_nanite_enabled:

                # CHECK 2: Is it on the Ignore List?
                name = str(asset_data.asset_name).lower()
                if any(term in name for term in ignore_terms):
                    ignored_count += 1
                    continue

                # REPORT IT
                logger.info('[ALERT] Nanite OFF: %s', asset_data.package_name)
                found_count += 1

    print('-' * 55)
    logger.info('Scan Complete.')
    logger.info(' > Suspicious Non-Nanite Meshes: %d', found_count)
    logger.info(' > Ignored (Glass/Window):       %d', ignored_count)
    print('-' * 55)


if __name__ == '__main__':
    audit_nanite_settings()