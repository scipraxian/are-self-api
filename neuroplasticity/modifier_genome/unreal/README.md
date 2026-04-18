# Unreal Engine NeuralModifier

The Unreal Engine NeuralModifier extends Are-Self with the build, staging,
deployment, and shader-compilation pathways needed to drive an Unreal Engine 5
project end-to-end. It is the first NeuralModifier bundle in the system and
serves as the reference shape for everyone that follows.

## What it ships

- **6 UE Executables** (`UNREAL_CMD`, `UNREAL_AUTOMATION_TOOL`, `UNREAL_STAGING`,
  `UNREAL_RELEASE_TEST`, `UNREAL_SHADER_TOOL`, `VERSION_HANDLER`) plus their
  argument and switch definitions.
- **The UE Default Environment** with its ContextVariables (project file,
  workspace root, etc.) so a fresh install knows where to find the user's
  `.uproject`.
- **14 UE-named NeuralPathways** (Full Build, Deploy, Stage, RecordPSOs, Compile
  Shaders, etc.) with their full Neuron / Axon / NeuronContext / EffectorContext
  / EffectorArgumentAssignment closure.
- **Log-parser strategies** registered with `occipital_lobe.log_parser.LogParserFactory`
  so the Frontal Lobe can read UE log output.
- **Native handlers** registered with `central_nervous_system.neuromuscular_junction`
  for the UE-specific Executables listed above.

## Install

```
./manage.py build_modifier unreal
```

This copies `neuroplasticity/modifier_genome/unreal/` to `neural_modifiers/unreal/`
at the repo root, loads `modifier_data.json` into the database, records one
`NeuralModifierContribution` row per object created, and flips the bundle's
status to `INSTALLED`. After install, `./manage.py enable_modifier unreal`
flips it to `ENABLED`.

## Uninstall

```
./manage.py uninstall_modifier unreal
```

Walks every `NeuralModifierContribution` row in install order, deletes the
target object, removes the contribution rows, deletes `neural_modifiers/unreal/`
from disk, and flips status back to `DISCOVERED`. The `NeuralModifier` row
itself is preserved so the install history stays intact.

## License

MIT, matching Are-Self core.
