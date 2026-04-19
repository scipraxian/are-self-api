# NeuralModifier bundles — author's guide

A NeuralModifier is an installable bundle that extends Are-Self with new
data (Pathways, Executables, Environments, ContextVariables, Tools, …)
and the Python code that makes that data do something at runtime. Bundles
are never Django apps. They do not touch `INSTALLED_APPS`. They contribute
rows through a loader that records every object they create, so the
uninstaller can walk the contributions in reverse order and put the
database back the way it found it.

This document is for developers shipping a new bundle. If you just want
to install one someone else wrote, run `./manage.py build_modifier <slug>`
and stop reading.

The Unreal bundle (`modifier_genome/unreal/`) is the reference
implementation. Everything described below is demonstrated end-to-end
there.

## Directory layout

Each bundle lives at `neuroplasticity/modifier_genome/<slug>/`. The
`<slug>` is the bundle's identity — it matches the `slug` field in the
manifest and is the argument every management command takes.

```
neuroplasticity/modifier_genome/<slug>/
├── manifest.json          # bundle metadata + entry module list
├── modifier_data.json     # Django serialized rows to load on install
├── README.md              # end-user-facing overview of the bundle
└── code/
    └── <package_name>/    # Python package imported at boot
        ├── __init__.py    # re-imports submodules for side-effect registration
        └── …              # handlers, parsers, MCP tools, etc.
```

On install, the whole tree is copied verbatim to
`neural_modifiers/<slug>/` at the repo root. That runtime directory is
gitignored and treated as derived state — never edit it by hand. The
install copy is what actually gets imported at boot; the `modifier_genome/`
tree is the source of truth.

## Manifest schema

`manifest.json` is a JSON object. The following keys are required and
validated by the loader; installs fail loudly if any are missing:

- `slug` — filesystem slug; must equal the bundle's directory name.
- `name` — human-readable display name.
- `version` — semver string (e.g. `"1.0.0"`).
- `author` — string.
- `license` — SPDX identifier or free-form string.
- `entry_modules` — list of Python module paths (strings) that the
  loader imports at install and at every boot so the bundle's
  registration side-effects fire. These modules must be importable from
  `<bundle>/code/` once that directory is on `sys.path`.

Additional keys (`description`, `requires_are_self`, any other metadata
the author wants) are allowed but not validated. See the Unreal manifest
for a working example.

### Manifest hash

On install the loader computes `sha256(manifest.json bytes).hexdigest()`
and stores it on the `NeuralModifier` row. On every boot it recomputes
the hash from disk and compares. A mismatch flips the bundle to `BROKEN`
and skips its entry-module import. This is a drift detector, not a
security boundary — edit the manifest, the bundle stops booting until
it is re-installed.

## `modifier_data.json` — contribution data

`modifier_data.json` is a JSON array of Django-serialized model
instances, exactly the format `django.core.serializers.serialize('json', …)`
produces. The loader walks the array in order, calls `save()` on each
deserialized object, and records one `NeuralModifierContribution` row
per save — pointing at the new object via a generic foreign key
(`content_type` + `object_id`).

Rules:

- **Use UUID primary keys.** Every model contributed by a bundle must
  have a `UUIDField` PK. Serialize the PK into the file; do not rely on
  auto-assignment. This keeps installs idempotent and makes contribution
  tracking deterministic.
- **Generate PKs with `uuid.uuid4()`.** Never hand-type UUIDs and never
  reuse them across bundles. Collisions will clobber core data.
- **Order matters for intra-bundle FKs.** Rows are saved top-to-bottom.
  If Row B has an FK to Row A, A must appear first. Uninstall walks in
  reverse for the same reason.
- **Do not contribute rows that already exist in core fixtures.**
  Bundles add to the system; they do not patch. If you need to mutate a
  row owned by core, rethink the design — usually you want a new row
  that sits next to it.
- **No cross-bundle references.** A bundle may only FK to core rows or
  to rows it ships itself. Pointing at another bundle's data couples
  install order and breaks clean uninstall.

The Unreal bundle's `modifier_data.json` ships `ContextVariable`,
`Environment`, `Executable`, `NeuralPathway`, and the full
Neuron/Axon/NeuronContext/EffectorContext closure — a good reference
for what a non-trivial payload looks like.

## Entry modules and side-effect registration

Entry modules listed in `manifest.json` are imported at install time and
re-imported at every boot. The convention is that each entry module's
`__init__.py` re-exports the submodules that carry registration
side-effects:

```python
# code/<package_name>/__init__.py
from . import handlers       # noqa: F401 — registers native handlers
from . import log_parsers    # noqa: F401 — registers LogParserFactory strategies
```

The registries a bundle is expected to extend are all in core Are-Self:

- `central_nervous_system.effectors.effector_casters.neuromuscular_junction`
  — `register_native_handler(name, callable)` for effector-backed native
  handlers. Pair with `unregister_native_handler(name)`.
- `parietal_lobe.parietal_mcp.gateway` —
  `register_parietal_tool(name, coroutine)` for MCP tools the Parietal
  Lobe exposes to reasoning. Pair with `unregister_parietal_tool(name)`.
- `occipital_lobe.log_parser.LogParserFactory` —
  `LogParserFactory.register(log_type, strategy_cls)` for log-parser
  strategies.

### Idempotent registration

`boot_bundles()` pops every entry module out of `sys.modules` and
re-imports it on each AppConfig ready pass. That means registration code
runs more than once in the life of a process. The convention is
**unregister-then-register**:

```python
unregister_native_handler('update_version_metadata')
register_native_handler('update_version_metadata', update_version_metadata)

unregister_parietal_tool('mcp_run_unreal_diagnostic_parser')
register_parietal_tool('mcp_run_unreal_diagnostic_parser',
                       mcp_run_unreal_diagnostic_parser)
```

The second import must not raise. A bundle whose entry module fails on
re-import will be flipped to `BROKEN` at boot.

### ToolDefinition rows and Parietal gating

If a bundle contributes a `ToolDefinition` row (via `modifier_data.json`)
*and* registers a matching `mcp_*` coroutine with
`register_parietal_tool`, the Parietal Lobe will include that tool in a
session's tool manifest only while the bundle is `ENABLED`. The gating
is a query-layer `Exists()` filter on `NeuralModifierContribution`;
disabling a bundle hides its tools from reasoning starting with the next
session, and enabling puts them back.

Core tools — `ToolDefinition` rows with no contribution row pointing at
them — are never filtered. A bundle's lifecycle only affects the rows it
created.

## Bundle lifecycle — commands and status

Every bundle moves through a small state machine on the `NeuralModifier`
row. Management commands are the supported way to drive it:

- `./manage.py build_modifier <slug>` — installs from
  `modifier_genome/<slug>/`. Copies to `neural_modifiers/<slug>/`,
  validates the manifest, imports entry modules, loads
  `modifier_data.json`, writes one contribution row per saved object.
  Status: `DISCOVERED` or fresh → `INSTALLED`. A failure mid-install
  flips the row to `BROKEN`, removes the runtime tree, and re-raises.
- `./manage.py enable_modifier <slug>` —
  `INSTALLED` or `DISABLED` → `ENABLED`. This is the only state that
  exposes bundle-contributed Parietal tools to reasoning.
- `./manage.py disable_modifier <slug>` —
  `ENABLED` → `DISABLED`. Code stays on `sys.path`, DB rows stay intact,
  bundle-contributed tools drop out of tool manifests on the next
  session.
- `./manage.py uninstall_modifier <slug>` — walks every contribution in
  reverse install order, deletes each target, removes the contribution
  rows, deletes `neural_modifiers/<slug>/` from disk. Status flips to
  `DISCOVERED`. The `NeuralModifier` row itself is preserved so the
  install history stays intact.
- `./manage.py list_modifiers` — read-only dump of every
  `NeuralModifier` row (status, version, contribution count, last
  install timestamp).

`AppConfig.ready()` calls `boot_bundles()` on process start. That walks
`neural_modifiers/`, verifies each manifest hash, puts each bundle's
`code/` on `sys.path`, and re-imports its entry modules. Hash drift or
an ImportError flips that bundle to `BROKEN` and skips the import; the
rest of the system keeps booting.

## Authoring checklist

1. Create `neuroplasticity/modifier_genome/<slug>/` with a `manifest.json`
   whose `slug` field equals the directory name.
2. Write `code/<package_name>/` with an `__init__.py` that imports every
   submodule that registers handlers, tools, or parsers. Use
   unregister-then-register for every registration call.
3. Generate seed rows programmatically (Django shell is fine), dump them
   with `django.core.serializers.serialize('json', queryset, indent=2)`,
   write to `modifier_data.json`. Make sure every PK is a `uuid.uuid4()`.
4. Add `<package_name>` to `manifest.json`'s `entry_modules`.
5. Run `./manage.py build_modifier <slug>`, then
   `./manage.py enable_modifier <slug>`.
6. Confirm behavior end-to-end, then
   `./manage.py uninstall_modifier <slug>` and re-install to verify the
   round-trip is clean — this is the real acceptance test for a bundle.

## Reference implementation

The Unreal bundle at `modifier_genome/unreal/` exercises every concept
in this document: entry-module side-effect registration for native
handlers and log parsers, a non-trivial `modifier_data.json` with
intra-bundle FKs, a contributed `ToolDefinition`
(`mcp_run_unreal_diagnostic_parser`) with a matching coroutine that
goes through Parietal gating, and the unregister-then-register pattern
for re-import idempotency. Read that bundle's source before starting a
new one.
