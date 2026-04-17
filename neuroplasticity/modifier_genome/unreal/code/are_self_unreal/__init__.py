"""Unreal NeuralModifier entry point.

Importing this package triggers side-effect registration of Unreal Engine
native handlers into central_nervous_system.neuromuscular_junction and
UE log parser strategies into occipital_lobe.log_parser.LogParserFactory.

Both submodules are imported here so either import target
(`are_self_unreal` or `are_self_unreal.handlers`) activates the full
registration surface.
"""
from . import handlers  # noqa: F401 # registers UE native handlers with NMJ
from . import log_parsers  # noqa: F401 # registers UE strategies with LogParserFactory
