# Unreal NeuralModifier — End-to-End Handoff

> **Purpose.** Hand the next session (new agent or rehydrated context)
> everything it needs to round-trip the Unreal bundle today.
> Self-contained. Read this first; branch out only when steps reference
> another file.

## Goal

Round-trip the Unreal NeuralModifier end-to-end within the next few
hours. Install → enable → exercise → disable → re-enable → uninstall.
The DB must look identical before the first install and after the
final uninstall. The full test suite must stay green both with and
without the bundle installed.

## Vocabulary (locked — do not drift)

- The thing is a **NeuralModifier**. Never "plugin."
- Archive (committed, source of truth): `neuroplasticity/genomes/<slug>.zip`.
- Runtime install tree (gitignored, per-machine): `neuroplasticity/grafts/<slug>/`.
- Scratch (gitignored, empty between ops): `neuroplasticity/operating_room/`.
- Payload file (inside the zip): `modifier_data.json`.
- Install path: Modifier Garden UI → `POST /api/v2/neural-modifiers/catalog/<slug>/install/`.
  Equivalent shell: `loader.install_bundle_from_archive(Path('neuroplasticity/genomes/unreal.zip'))`.

## Reference pointers

- **Feature narrative.** `are-self-docs/docs/brain-regions/neuroplasticity.md` — the prose story of how it all fits together. Read this if you're cold to the domain.
- **Completion plan.** `NEURAL_MODIFIER_COMPLETION_PLAN.md` — tracks outstanding tasks.
- **Loader.** `neuroplasticity/loader.py` — install / uninstall / enable / disable / boot. Public API: `install_bundle_from_archive`, `uninstall_bundle`, `enable_bundle`, `disable_bundle`, `upgrade_bundle`.
- **Bundle archive.** `neuroplasticity/genomes/unreal.zip` — committed. Contains `manifest.json`, `modifier_data.json`, `code/are_self_unreal/` at its top level.

## What's landed and green

- Models: `NeuralModifier`, `NeuralModifierContribution` (GFK with `UUIDField` object_id), `NeuralModifierInstallationLog`, `NeuralModifierInstallationEvent`, two enum tables.
- Loader with transactional install/uninstall. AVAILABLE = zip on disk AND no DB row; uninstall DELETES the row and everything CASCADEs.
- Management commands: `enable_modifier`, `disable_modifier`, `uninstall_modifier`, `upgrade_modifier`, `list_modifiers`. (`build_modifier` and `pack_modifier` retired — the zip is the single source of truth.)
- `AppConfig.ready()` boot hook with SHA-256 manifest-hash verification. Hash drift → BROKEN.
- Three registration surfaces, each with unregister pair + collision detection:
  - `register_native_handler` / `unregister_native_handler` in `central_nervous_system/effectors/effector_casters/neuromuscular_junction.py`
  - `register_parietal_tool` / `unregister_parietal_tool` in `parietal_lobe/parietal_mcp/gateway.py`
  - `LogParserFactory.register` in `occipital_lobe/log_parser.py`
- Parietal tool-set gating on ENABLED.
- Modifier Garden REST surface: catalog list / install / uninstall / enable / disable / delete.
- The Unreal bundle's round-trip test lives at `neuroplasticity/tests/test_install_unreal_bundle.py` (6 scenarios, install/uninstall/reinstall idempotency, operating_room cleanup, soft-lookup on M2M edges).

## Known risks going into E2E

1. **Audit for UE-named rows in core fixtures.** If any UE-specific `Executable`, `ExecutableArgument`, `EffectorContext`, `Neuron`, `Axon`, `NeuronContext`, `NeuralPathway`, `ToolDefinition`, or `ToolParameter` still lives in a core fixture (not inside the zip's `modifier_data.json`), Step 1's "core-only" check won't prove clean isolation and Step 9's uninstall-round-trip check will mislead.
2. **BROKEN boot transitions.** Unit-test-covered; not exercised in E2E against the real bundle. If something goes sideways around boot-time hash verification, capture the specific failure — there is no pre-written repro against the Unreal bundle specifically.

## Pre-flight

Before touching the bundle, confirm the baseline.

```
cd C:\Users\micha\are-self\are-self-api
./manage.py test neuroplasticity parietal_lobe central_nervous_system
```

Expect all green. If red: **stop and fix first.** Don't fight two problems at once.

Also confirm the runtime tree is clean — a stale `neuroplasticity/grafts/unreal/` from a prior run will make install fail with `FileExistsError`:

```
>>> from pathlib import Path
>>> Path('neuroplasticity/grafts/unreal').exists()  # should be False
```

If it exists, `./manage.py uninstall_modifier unreal` first (if the row exists) or just `rm -rf neuroplasticity/grafts/unreal` (if it doesn't). And confirm `neuroplasticity/operating_room/` has no leftover tempdirs; if it does, delete them — the root itself must stay.

## The Nine-Step E2E Protocol

### Step 1 — Core-only fixture load (no bundle)

Fresh DB, load the four core fixture tiers per `are-self-install.bat`:

```
./manage.py flush --noinput
./manage.py migrate
# Load each app's genetic_immutables, zygote, initial_phenotypes in
# the order install.bat uses.
```

**Check for UE leakage:**

```
./manage.py shell
>>> from environments.models import Executable
>>> Executable.objects.filter(name__icontains='unreal').count()
>>> Executable.objects.filter(name='VERSION_HANDLER').count()
>>> from parietal_lobe.models import ToolDefinition
>>> ToolDefinition.objects.filter(name='mcp_run_unreal_diagnostic_parser').count()
>>> from neuroplasticity.models import NeuralModifier
>>> NeuralModifier.objects.count()   # AVAILABLE = no row; expect 0
```

Expected: **all zeros.** Under the new AVAILABLE = no-DB-row ruling, a bundle that hasn't been installed yet has zero `NeuralModifier` rows — the zip is what signals availability.

If UE-named rows appear here: **stop.** Finish moving those rows to `modifier_data.json` (inside the zip) before proceeding. Preserve the UUID literal, remove the entry from its core fixture, re-pack the zip (either via a one-shot helper or by editing the extracted contents and re-zipping).

Also run the full test suite here as a **core-only baseline**:

```
./manage.py test
```

Record pass/fail counts. This is what Step 9 must match.

### Step 2 — Install the bundle

Via the Modifier Garden UI: click Install on the Unreal row. Shell equivalent:

```
./manage.py shell
>>> from pathlib import Path
>>> from neuroplasticity import loader
>>> loader.install_bundle_from_archive(Path('neuroplasticity/genomes/unreal.zip'))
```

Expected return: a `NeuralModifier` row with `status=Installed`, `contributions=N` where N equals the row count in the zip's `modifier_data.json` (currently 260).

**Failure decode:**

- `FileNotFoundError` → `neuroplasticity/genomes/unreal.zip` missing. Impossible on a checked-out repo; suspect working-directory confusion.
- `FileExistsError` → stale `neuroplasticity/grafts/unreal/`. Pre-flight step should have cleared this. No DB row was created — the pre-flight check runs before any writes.
- `ValueError` about manifest keys → the zip's manifest is missing one of `slug`, `name`, `version`, `author`, `license`, `entry_modules`.
- Deserialization error (`DeserializationError`) → `modifier_data.json` references an FK target that doesn't exist in core fixtures. Either add the target to core or remove the row from the bundle.
- Entry-module `ImportError` → `are_self_unreal/handlers.py` or `log_parsers.py` imports failed. Common cause: circular import with core. Break with a lazy import. The `NeuralModifier` row created during install will be DELETED on failure — AVAILABLE state is restored automatically.
- `RuntimeError` about duplicate registration → entry-module registered a slug that was already live. Wrap with `unregister_*(slug)` first.

Post-failure, confirm `operating_room/` is empty (success OR failure — invariant):

```
>>> list(Path('neuroplasticity/operating_room').iterdir())  # should be []
```

### Step 3 — Verify post-install state

```
./manage.py list_modifiers
```

Expected: `unreal   Installed  v1.0.0  contributions=N  last=<timestamp>`.

```
>>> from neuroplasticity.models import NeuralModifierContribution
>>> NeuralModifierContribution.objects.filter(neural_modifier__slug='unreal').count()  # = N
>>> from environments.models import Executable
>>> Executable.objects.filter(name__icontains='unreal').exists()  # True now
>>> Path('neuroplasticity/grafts/unreal').is_dir()  # True
>>> list(Path('neuroplasticity/operating_room').iterdir())  # []
```

### Step 4 — Enable

```
./manage.py enable_modifier unreal
./manage.py list_modifiers
```

Expected: status = `Enabled`.

### Step 5 — Full test suite with the bundle installed

```
./manage.py test
```

Expected: all green. If a test passed in Step 1's core-only baseline but fails here, the bundle's install changed core behavior — that's a bug in the bundle, not in the test.

### Step 6 — Exercise in a live reasoning session

This is the "it actually works" proof.

```
./manage.py runserver
```

From the UI:

1. Start a reasoning session with an Identity that has UE tools enabled on its IdentityDisc.
2. Ask the LLM to trigger a short UE pathway (Compile Shaders is shortest; Deploy is the most representative).
3. Watch the logs.

**Heuristic checks (pick the ones you can observe):**

- The tool manifest the LLM sees includes `mcp_run_unreal_diagnostic_parser`. → Parietal gating is live + bundle is ENABLED.
- A UE build or run log file parses into structured output via `LogParserFactory`. → Log-parser strategy registered and dispatching.
- The `update_version_metadata` native handler fires when its slug is invoked. → Native-handler registration live.
- ContextVariables from the bundle's `modifier_data.json` resolve in effector argument rendering. → Fixture payload landed correctly.

### Step 7 — Disable, verify tools drop

```
./manage.py disable_modifier unreal
```

Start a **new** reasoning session (the gating filter runs per session, so an in-flight session keeps its tools). Inspect the tool manifest:

```
>>> from frontal_lobe.models import ReasoningSession
>>> from parietal_lobe.parietal_lobe import ParietalLobe
>>> session = ReasoningSession.objects.filter(status_id=<ACTIVE>).latest('created')
>>> lobe = ParietalLobe(session, lambda msg: None)
>>> import asyncio
>>> names = {s['function']['name'] for s in asyncio.run(lobe.build_tool_schemas())}
>>> 'mcp_run_unreal_diagnostic_parser' in names  # False
```

Note: native handlers stay registered in the process — `DISABLED` gates Parietal tools only, by design. Not a bug.

### Step 8 — Re-enable, verify tools return

```
./manage.py enable_modifier unreal
```

Repeat Step 7's tool-manifest probe in a new session. `mcp_run_unreal_diagnostic_parser` should reappear.

### Step 9 — Uninstall, verify clean slate

Via the Modifier Garden UI: click Uninstall. Shell equivalent:

```
./manage.py uninstall_modifier unreal
./manage.py list_modifiers
```

Expected: the `unreal` row is gone from `list_modifiers` output (AVAILABLE = no DB row).

**Clean-slate checks:**

```
>>> from neuroplasticity.models import NeuralModifier, NeuralModifierContribution
>>> NeuralModifier.objects.filter(slug='unreal').exists()  # False
>>> NeuralModifierContribution.objects.count()  # 0
>>> from environments.models import Executable
>>> Executable.objects.filter(name__icontains='unreal').count()  # 0
>>> from pathlib import Path
>>> Path('neuroplasticity/grafts/unreal').exists()  # False
>>> list(Path('neuroplasticity/operating_room').iterdir())  # []
>>> Path('neuroplasticity/genomes/unreal.zip').exists()  # True — the zip stays
```

Re-run the full test suite:

```
./manage.py test
```

**This result must match Step 1's core-only baseline exactly.** If a test passed in Step 1 and fails now, uninstall left debris. Capture the diff (`./manage.py dumpdata > post_uninstall.json`, compare against a pre-install dump), and add a regression test to `neuroplasticity/tests/test_modifier_lifecycle.py` before moving on.

### Pass criteria

All nine steps complete without errors. Step 9's test result equals Step 1's core-only baseline. The runtime tree at `neuroplasticity/grafts/unreal/` is gone. The `NeuralModifier` row is gone. The committed `neuroplasticity/genomes/unreal.zip` is untouched. `operating_room/` is empty.

## If E2E fails — likely culprits, in order

1. **Step 1 shows UE-named rows in core → audit fixtures.** Move them to `modifier_data.json` (UUID literal preserved) inside the zip, remove from core fixtures, re-run.
2. **Step 2 deserialization failure → bundle FK target missing from core.** Usually an `ExecutableType`, `ContextVariableType`, or `UseType`. Either add the type to core (if it's generic) or make it a bundle contribution (if it's UE-specific).
3. **Step 2 entry-module ImportError → circular import.** Lazy-import inside the function that needs the core module.
4. **Step 5 failure that wasn't in Step 1 → bundle mutates something core owns.** The bundle should only *add*. If tests see changed behavior on core-owned rows, the bundle is patching instead of contributing.
5. **Step 9 leaves rows behind → contribution GFK couldn't reach a target.** Audit bundle-contributed models for `UUIDField` PKs — an integer-PK model can't be tracked.

## After E2E passes

Update `NEURAL_MODIFIER_COMPLETION_PLAN.md`:

- Mark the consolidation patch landed (2026-04-20). Its two live bugs (staging leak, stuck row) are fixed; the three sibling root dirs are collapsed under `neuroplasticity/`; install/uninstall are round-trip-clean against the committed zip.
- Refresh the "Where we stand" section if it drifts.

Then pick from remaining backend work in priority order as captured in `NEURAL_MODIFIER_COMPLETION_PLAN.md` and `TASKS.md`.

Frontend MVP (separate track, backend-ready now):

- **FE-1** Modifier Garden list / install / uninstall
- **FE-2** Enable / disable toggles
- **FE-3** Row-level bundle attribution chips in existing editors
- **FE-4** Tool picker respects soft-lookup on orphaned UUIDs

## Context-handoff checklist for the next session

If a fresh Claude agent picks this up cold, it needs:

1. **This file** — current state + E2E protocol.
2. `are-self-docs/docs/brain-regions/neuroplasticity.md` — feature narrative.
3. `NEURAL_MODIFIER_COMPLETION_PLAN.md` — outstanding work items (its Landed section may lag — this file is the current-state source of truth for E2E).

Plus: awareness that **vocabulary is locked** (NeuralModifier, never plugin; the three dir names are `genomes/`, `grafts/`, `operating_room/`), **UUIDs are random `uuid.uuid4()`** (no namespaces), and **`INSTALLED_APPS` is never mutated at runtime**. Those three non-negotiables carry across every task.

## Mental model in one paragraph

A NeuralModifier is a bundle that contributes **data** (Django-serialized rows loaded from `modifier_data.json`, each tagged with a `NeuralModifierContribution` row pointing at it via a generic foreign key against `UUIDField` PKs) and **code** (registration calls into three module-level registries: NMJ native handlers, Parietal MCP tools, LogParserFactory strategies). Its lifecycle runs AVAILABLE (zip + no row) → INSTALLED → ENABLED ↔ DISABLED → AVAILABLE (uninstall deletes the row). BROKEN is reserved for boot-time drift. Install extracts the zip into `operating_room/`, copies into `grafts/<slug>/`, writes rows + contribution rows, and nukes the tempdir; uninstall walks contributions in reverse install order, deletes targets + contribution rows, deletes the runtime tree, then deletes the `NeuralModifier` row (logs and events CASCADE). Enable / disable is a status flip that only the Parietal tool-set filter reads (handlers and parsers don't gate). `INSTALLED_APPS` is immutable across all of it. Everything hashes; everything logs.
