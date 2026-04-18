"""Unreal Engine native-handler and parietal-tool registration.

Imports the NMJ native-handler registry and the ParietalMCP registry
surfaces and registers the UE pieces at import time. boot_bundles()
pops this module from sys.modules on every AppConfig.ready and
re-imports it, so registration must be idempotent — unregister first,
then register — or the second import would raise RuntimeError on the
already-registered slug.
"""

from central_nervous_system.effectors.effector_casters.neuromuscular_junction import (
    register_native_handler,
    unregister_native_handler,
)
from parietal_lobe.parietal_mcp.gateway import (
    register_parietal_tool,
    unregister_parietal_tool,
)

from .mcp_run_unreal_diagnostic_parser import (
    mcp_run_unreal_diagnostic_parser,
)
from .version_metadata_handler import update_version_metadata


unregister_native_handler('update_version_metadata')
register_native_handler('update_version_metadata', update_version_metadata)

unregister_parietal_tool('mcp_run_unreal_diagnostic_parser')
register_parietal_tool(
    'mcp_run_unreal_diagnostic_parser',
    mcp_run_unreal_diagnostic_parser,
)
