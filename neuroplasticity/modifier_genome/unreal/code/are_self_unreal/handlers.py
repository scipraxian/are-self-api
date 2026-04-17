"""Placeholder for Unreal Engine native handlers.

When populated, this module imports the NMJ native-handler registry from
central_nervous_system.neuromuscular_junction and registers UE-specific
handlers (UNREAL_CMD, UNREAL_AUTOMATION_TOOL, UNREAL_STAGING,
UNREAL_RELEASE_TEST, UNREAL_SHADER_TOOL, VERSION_HANDLER) against it.

Currently a no-op so the bundle loads cleanly. The actual handler
implementations migrate in a follow-up pass once the bundle pipeline
is proven.
"""
