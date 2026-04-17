"""Placeholder for Unreal Engine log parser strategies.

When populated, this module imports LogParserFactory from
occipital_lobe.log_parser and calls LogParserFactory.register(...) for
each UE log variant recognized by ue_tools. Registration is idempotent
and safe to re-run.

Currently a no-op so the bundle loads cleanly.
"""
