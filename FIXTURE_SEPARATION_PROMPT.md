# Pass 2 — Fixture Tier Split + Unreal Modifier Extraction

Read CLAUDE.md, STYLE_GUIDE.md, and this entire document before making any
changes. This is the executable prompt for finishing the `uuid-migration`
branch. Pass 1 is merged and locked. Pass 2 is what's left.

---

## Ground Rules (read first, re-read if in doubt)

1. **Investigate before asserting.** Investigation is always authorized.
   If you are about to guess at a model reference, a field name, a fixture
   value, or an import path — stop and look it up. Reading files is free.
   Guessing costs us a correction round-trip.

2. **UUIDs are `uuid.uuid4()` random literals.** No namespaces, no seeds,
   no derivation schemes, no constants in `common/constants.py` for
   fixture UUID generation. Any new UUID written to a fixture, a model
   class constant, or a migration uses `uuid.uuid4()`. Existing UUID
   literals already in fixtures are **frozen values** — they are opaque
   and do not get regenerated.

3. **Vocabulary is locked.** The renamed plugin app is `neuroplasticity`.
   Installable bundles are `NeuralModifier`s. The committed source tree
   lives at `neuroplasticity/modifier_genome/<slug>/`. The runtime install
   tree lives at `neural_modifiers/<slug>/` (repo-root, gitignored).
   Bundle payload file is `modifier_data.json`. The build command is
   `./manage.py build_modifier`. Do not use the word "plugin" in new
   code, new docstrings, or new commit messages. Existing legacy
   occurrences in untouched files are deferred to Task 7.

4. **Immutability directive.** Anything not truly immutable uses UUID
   primary keys. Protocol enums and canonical vocabulary tables with
   class-level integer constants are the only things that keep integer
   PKs. Everything else — and especially anything a `NeuralModifier`
   might ever contribute rows to — is UUID-keyed. This directive is
   project-wide and standing.

5. **House style.** `Optional[str]` not `str | None`. 88-char lines.
   Single quotes. `%s` logging, not f-strings. No nested functions.
   See STYLE_GUIDE.md for the rest.

6. **Commits only on request.** Do not commit unless Michael explicitly
   asks. Stage, report, wait.

7. **Give yourself breathing room.** If a task looks like it's going
   to touch more than you expected, stop and report scope before
   executing. Michael would rather hear "Task 5b touches 47 files"
   than see 47 files change without warning.

---

## What Pass 1 Locked In

Pass 1 flipped 18 plugin-extensible models from integer to UUID PKs on
the `uuid-migration` branch. 433 tests pass. The migration mapping is
recorded at `uuid_migration_mapping.json` at repo root — old integer
PK → new UUID literal, one entry per migrated model.

**The 18 models (UUID-keyed as of Pass 1):**

- `central_nervous_system`: `Effector`, `EffectorContext`,
  `EffectorArgumentAssignment`, `Neuron`, `NeuronContext`, `Axon`
- `environments`: `Executable`, `ExecutableSwitch`, `ExecutableArgument`,
  `ExecutableArgumentAssignment`, `ContextVariable`
- `parietal_lobe`: `ToolDefinition`, `ToolParameter`,
  `ToolParameterAssignment`, `ParameterEnum`
- `hypothalamus`: `AIModelDescription`
- `temporal_lobe`: `IterationDefinition`, `IterationShiftDefinition`

Plus the already-UUID-keyed models that predate Pass 1: `Identity`,
`IdentityDisc`, `ProjectEnvironment`, `NeuralPathway`.

**Model class UUID constants** (`Effector.BEGIN_PLAY`, `LOGIC_GATE`,
`FRONTAL_LOBE`, `DEBUG`, `Executable.BEGIN_PLAY`, `PYTHON`, `DJANGO`,
`UNREAL_CMD`, `UNREAL_AUTOMATION_TOOL`, `UNREAL_STAGING`,
`UNREAL_SHADER_TOOL`, `VERSION_HANDLER`, `DEPLOY_RELEASE`, etc.) are
frozen `uuid.UUID(...)` literals. The frontend's `nodeConstants.ts`
mirrors them as UUID strings — the companion PR gates the branch merge.

## What Pass 2 Did Before This Prompt Was Rewritten

If you are resuming mid-session, the following Pass 2 work is already
on disk and staged but **not yet committed**:

- **Task 2 — zygote seed.** `hypothalamus/fixtures/zygote.json` created
  with 4 `AIModel` rows (nomic-embed-text, llama3.2:3b, qwen2.5-coder:7b,
  gemma3:4b). These are frozen literals — do not regenerate.
- **Task 3 — log-merge move.** `ue_tools/merge_logs.py` and
  `ue_tools/merge_logs_nway.py` moved to `occipital_lobe/`, with tests.
  Import in `central_nervous_system/views/spike_merge_viewset.py` flipped.
  15 tests pass.
- **Task 4 — log_parser split.** `occipital_lobe/log_parser.py` now
  holds the generic core (`LogConstants`, `LogStats`, `LogEntry`,
  `LogSession`, `LogParserStrategy` ABC, registry-based
  `LogParserFactory`, `merge_sessions`). `ue_tools/log_parser.py` now
  holds the UE-augmented constants, `UELogParserStrategy`, and the
  two UE strategies, and re-exports for backward compat. Side-effect
  registrations with `# noqa: F401 # registers UE strategies with
  LogParserFactory` at `central_nervous_system/views/spike_merge_viewset.py`
  and `occipital_lobe/tests/test_merge_logs_nway.py`. 33 passed,
  1 skipped.
- **Task 4.5 — environments UUID flip.**
  `ProjectEnvironmentContextKey`, `ProjectEnvironmentStatus`, and
  `ProjectEnvironmentType` now inherit `(UUIDIdMixin, NameMixin)`.
  `environments/migrations/0001_initial.py` patched in place.
  `environments/fixtures/initial_data.json` has its 16 PKs flipped
  with FK rewrites in `contextvariable.key`, `projectenvironment.type`,
  and `projectenvironment.status`. Three new entries added to
  `uuid_migration_mapping.json`. The literals in the fixture are
  **frozen as-is** — do not regenerate them.
- **`neuroplasticity/models.py`** — the app is registered and its
  models are defined: `NeuralModifierStatus`, `NeuralModifier`,
  `NeuralModifierContribution` (GFK with UUIDField `object_id`),
  `NeuralModifierInstallationLog`, `NeuralModifierInstallationEventType`,
  `NeuralModifierInstallationEvent`. Helper methods
  `current_installation()` and `iter_contributed_objects()` are
  present. **Docstring drift**: the file still uses legacy
  "plugin" / "plugins_runtime" / "plugin_data.json" language in the
  module and class docstrings. Task 7 fixes that.
- **`neuroplasticity/fixtures/reference_data.json`** — the 5 status
  rows and 6 event-type rows (integer PKs 1–5 and 1–6). This file
  gets renamed to `genetic_immutables.json` in Task 5a.

If any of the above is already committed when you start, skip it.
If none of it is committed, stage it into the Task 5 commit sequence
described below.

---

## The Four Fixture Tiers

Every app's fixtures directory converges on up to four files, named
for their biological role:

### `genetic_immutables.json`
- Integer-PK protocol enums and canonical vocabulary tables only.
- Things like `SpikeStatus`, `AxonType`, `CNSDistributionMode`,
  `NeuralModifierStatus`, `NeuralModifierInstallationEventType`,
  `IdentityAddonPhase`, `BudgetPeriod`, `AIModelCapabilities`,
  `AIModelRole`, `AIModelQuantization`, `AIModelFamily`, `SyncStatus`,
  etc. If it has a class-level integer constant, it lives here. Note
  that `ProjectEnvironmentContextKey`, `ProjectEnvironmentStatus`, and
  `ProjectEnvironmentType` are NO LONGER integer-keyed as of Task 4.5
  — they moved to UUID and ship in `zygote.json` / `initial_phenotypes.json`.
- **Loaded by:** install script (always), Docker (always), tests (always).
- **Rule:** No UUID records. No instance data. Pure vocabulary.
  Never-delete, never-renumber. Each PK is a forever contract.

### `zygote.json`
- The minimum UUID-keyed rows the system needs to *boot* and to bind
  one end-to-end identity thread for tests.
- Examples: `nomic-embed-text` (hard-coded at `hippocampus/models.py:87`
  — embedding pipeline can't boot without it), the single canonical
  `Identity` + `IdentityDisc` tests bind to, the default
  `ProjectEnvironment` referenced by `central_nervous_system/utils.py`.
- **Loaded by:** install script (always), Docker (always), tests (always).
- **Rule:** UUID-keyed. Minimum viable — if boot / tests / install
  works without a row, it does not belong here. Cross-app FKs are
  permitted because `zygote.json` loads in a single `loaddata` pass.

### `initial_phenotypes.json`
- The rest of the committed-to-core structural rows that ship to end
  users out-of-the-box: canonical ContextKeys, sample ContextVariables,
  the core set of Effectors / Neurons / Axons / NeuralPathways that
  are NOT destined for the Unreal `NeuralModifier`, the reference
  iteration definitions, etc.
- **Loaded by:** install script (always), Docker (always). **Tests
  do NOT load this file.**
- **Rule:** UUID-keyed. Everything the transitive-closure pass
  identifies as "stays in core."

### `petri_dish.json`
- Test-only instance rows. Minimal. Whatever `CommonFixturesAPITestCase`
  needs that `zygote.json` doesn't already provide.
- **Loaded by:** tests only.
- **Rule:** UUID-keyed. Self-contained. Must not depend on rows in
  `initial_phenotypes.json`.

**Not every app needs all four files.** Apps with only protocol enums
(e.g. `frontal_lobe`, `prefrontal_cortex`) ship only
`genetic_immutables.json`. Apps with no fixtures at all ship nothing.

### Load Order

**Install / Docker:**
`genetic_immutables` → `zygote` → `initial_phenotypes`

**Tests (`CommonFixturesAPITestCase`):**
`genetic_immutables` → `zygote` → `petri_dish`

`CommonTestCase` (the leaner base) loads only `genetic_immutables`.

`genetic_immutables.json` is NOT a Django magic name the way
`initial_data.json` was. Test base classes must list each app's
fixture file explicitly. Install script does the same.

---

## Directory Model: modifier_genome vs. neural_modifiers

Two directories, two purposes:

- **`neuroplasticity/modifier_genome/<slug>/`** — committed source.
  This is the canonical, version-controlled source tree for every
  first-party `NeuralModifier` bundle that ships in the repo. The
  Unreal extraction lives at `neuroplasticity/modifier_genome/unreal/`.
  Structure per bundle:
  ```
  modifier_genome/<slug>/
    manifest.json
    modifier_data.json
    code/
      <python modules>
    README.md
  ```
  The `./manage.py build_modifier <slug>` command (Task 6) reads this
  tree, validates the manifest, and produces an installable zip.

- **`neural_modifiers/<slug>/`** — runtime install tree, at repo root.
  **Gitignored.** When a bundle is installed (via `build_modifier` +
  loader, or eventually via the modifier garden), it is unzipped here.
  `sys.path` is extended to include `neural_modifiers/<slug>/code/`
  at boot. Uninstall deletes the directory and replays the frozen
  manifest from `NeuralModifierInstallationLog` to remove contributed
  DB rows (walking `NeuralModifier.iter_contributed_objects()`).

`INSTALLED_APPS` is never mutated at runtime. Contributions are data,
not app registration.

---

## The `neuroplasticity` Models (Already on Disk)

`neuroplasticity/models.py` defines the lifecycle and uninstall-manifest
tables. Summary for reference:

- **`NeuralModifierStatus`** (int-PK, integer class constants 1–5):
  `DISCOVERED → INSTALLED → ENABLED ⇄ DISABLED`, with `BROKEN` as a
  terminal error state. Lives in `genetic_immutables.json`.

- **`NeuralModifier`** (UUID PK via `DefaultFieldsMixin`): one row per
  installed bundle. `slug`, `version`, `author`, `license`,
  `manifest_hash`, `manifest_json`, FK to status. Helper methods:
  `current_installation()` returns the most-recent
  `NeuralModifierInstallationLog` or `None`; `iter_contributed_objects()`
  yields each live GFK contribution target in install order, skipping
  orphans silently.

- **`NeuralModifierContribution`** (`CreatedMixin`): one row per DB
  object a modifier created on install. GFK via `content_type` +
  `object_id`. **`object_id` is a `UUIDField`** — this is the whole
  point of Pass 1: every contribution target is UUID-keyed, so a
  single UUID column handles every content type. Protocol enums are
  never contribution targets.

- **`NeuralModifierInstallationLog`** (`CreatedMixin`, FK to
  `NeuralModifier` with `related_name='installation_logs'`): one row
  per install attempt. `installation_manifest` JSONField is a frozen
  snapshot of the manifest at install time. Reinstall creates a new
  log row — history is retained.

- **`NeuralModifierInstallationEventType`** (int-PK, class constants
  1–6): `INSTALL`, `UNINSTALL`, `ENABLE`, `DISABLE`, `LOAD_FAILED`,
  `HASH_MISMATCH`. Lives in `genetic_immutables.json`.

- **`NeuralModifierInstallationEvent`** (`CreatedMixin`, FK to log
  with `related_name='events'`, FK to event type, `event_data`
  JSONField): append-only per-step events within an install attempt.

**Docstring drift warning.** These models currently document
themselves in the legacy "plugin" vocabulary ("plugin bundle",
"plugins_runtime/", "plugin_data.json"). Task 7 rewrites them into
the locked neuroplasticity vocabulary. Do not touch them before then
unless you are explicitly doing Task 7.

---

## Transitive Closure — What Goes in the Unreal Modifier

The Unreal extraction is driven top-down from `Executable` roots that
are UE-specific. Walk the FK graph:

```
Executable (UE-specific roots)
  → ExecutableArgument / ExecutableSwitch (UE-flavored)
  → Effector (UE-flavored)
    → EffectorContext / EffectorArgumentAssignment
    → Neuron (UE-flavored)
      → NeuronContext
      → Axon
        → NeuralPathway (UE-flavored)
```

Everything the closure reaches that is **exclusively** UE gets pulled
out of core fixtures and into
`neuroplasticity/modifier_genome/unreal/modifier_data.json`. Mixed
pathways (core atoms composed into UE-shaped flows) were resolved in
planning as **Option B: move the whole pathway to the bundle**. The
atoms stay in core; the pathway identity is UE and goes to the bundle.
FK direction Neuron → Effector into core is fine and expected.

Integer-PK rows with UE flavor (e.g. a `ProjectEnvironmentContextKey`
row whose semantic is UE-specific) — these are the reason Task 4.5
flipped those three models to UUID PKs in the first place. After
Task 4.5 the UE-flavored rows are normal UUID rows and slot cleanly
into `modifier_data.json`.

Legacy cleanup surfaced during closure:

- `update_version_metadata` is UE-specific. Move to bundle.
- `deploy_release_test` is legacy. Remove entirely.

The full closure inventory is expected to be produced during Task 1
below and reported back before any moves happen.

---

## Registration Seams

Two places in core that discover bundle contributions at runtime
without mutating `INSTALLED_APPS`. Task 6 wires the loader to walk
both.

1. **`central_nervous_system/neuromuscular_junction.py` native-handler
   dict.** The Unreal bundle's `update_version_metadata` native handler
   registers into this dict at import time via a side-effect import
   (`# noqa: F401`). The loader imports every
   `neural_modifiers/<slug>/code/<slug>/registrations.py` (or
   equivalent entry point declared in the manifest) at boot, which
   triggers the side-effect registration.

2. **`LogParserFactory.register(...)` registry in
   `occipital_lobe/log_parser.py`.** The UE log parser strategies
   (`UEBuildLogStrategy`, `UERunLogStrategy`) register themselves via
   the same side-effect-import mechanism. Task 4 already installed the
   factory and the UE-side registration calls. The loader uses the
   same entry-point import to reach them.

Any new seam discovered during Task 1 gets reported, not silently
added.

---

## Task Sequence

Each task should be bisectable. Stage work, report, wait for a commit
signal before moving on.

### Task 1 — Orientation and Transitive Closure Inventory

**Output only, no code changes.**

1. Read `CLAUDE.md`, `STYLE_GUIDE.md`, and this file in full.
2. Read `neuroplasticity/models.py`, `neuroplasticity/fixtures/reference_data.json`,
   `uuid_migration_mapping.json`, and `common/management/commands/core_dump.py`.
3. Skim `ue_tools/`, `occipital_lobe/log_parser.py`,
   `central_nervous_system/neuromuscular_junction.py`, and
   `environments/models.py` for current state.
4. Produce:
   - The full transitive-closure inventory from UE `Executable` roots
     — every model and every row that should end up in
     `modifier_genome/unreal/modifier_data.json`.
   - The "stays in core" complement for `initial_phenotypes.json`.
   - The list of legacy removals (`deploy_release_test`, etc.).
   - Any newly discovered registration seams.
   - A per-app fixture-tier plan showing which of the four files
     each app will end up with.
5. Report. Wait.

### Task 5a — Rename the immutables file

1. `git mv neuroplasticity/fixtures/reference_data.json neuroplasticity/fixtures/genetic_immutables.json`
2. No other changes. Tests still pass because nothing references the
   old name yet.
3. Report. This is the rename plumbing proof.

### Task 5b — Split one reference app (environments)

1. Take `environments/fixtures/initial_data.json` (already flipped in
   Task 4.5) and split it into `genetic_immutables.json` /
   `zygote.json` / `initial_phenotypes.json` / `petri_dish.json` per
   the transitive-closure plan from Task 1.
2. Any new UUIDs written during the split are `uuid.uuid4()` random
   literals. Existing literals are frozen.
3. Delete `environments/fixtures/initial_data.json`.
4. Update `common/tests/common_test_case.py` — `CommonTestCase` lists
   every app's `genetic_immutables.json` explicitly;
   `CommonFixturesAPITestCase` adds `zygote.json` and `petri_dish.json`
   entries.
5. Update `are-self-install.bat` — replace the single `loaddata
   initial_data.json` with three explicit passes: immutables, zygote,
   phenotypes.
6. Run the full test suite. Fix FK breakage within the environments
   split. Do not touch other apps yet.
7. Report.

### Task 5c — Split the remaining apps

Top-down through the transitive closure order. For each app:

1. Split its `initial_data.json` into the tiers it needs.
2. UE-flavored rows identified by Task 1 are **held aside** in a
   scratch file, not written to core tiers — they are destined for
   Task 5d.
3. Delete the old `initial_data.json`.
4. Extend `CommonTestCase` / `CommonFixturesAPITestCase` fixture
   lists to pick up the new files.
5. Run tests after each app. Keep commits bisectable — one app per
   commit is a reasonable cadence. Report at a cadence that gives
   Michael room to catch drift.

### Task 5d — Modifier bundle directory and UE row relocation

1. Create `neuroplasticity/modifier_genome/unreal/` with:
   - `manifest.json` (slug, version, author, license, entry points,
     declared contributions, declared registration seams)
   - `modifier_data.json` (the held-aside UE rows from Task 5c)
   - `code/` (scaffolded; actual UE Python moves from `ue_tools/` in
     a follow-up if scoped in)
   - `README.md`
2. Add `.gitkeep` to `neuroplasticity/modifier_genome/` and gitignore
   `/neural_modifiers/` at repo root.
3. Delete `ollama_fixture_generator.py`. It is obsolete — its output
   is captured as frozen literals in `hypothalamus/zygote.json`.
4. Run tests. Report.

### Task 6 — `build_modifier` + contribution-aware loader

1. `./manage.py build_modifier <slug>` — reads
   `neuroplasticity/modifier_genome/<slug>/`, validates the manifest,
   hashes it, zips the bundle, emits the install-ready artifact.
2. Loader at boot:
   - Scans `neural_modifiers/*/` for installed bundles.
   - For each, verifies `manifest_hash` against the recorded
     `NeuralModifier.manifest_hash`; mismatch → status `BROKEN`,
     log event `HASH_MISMATCH`.
   - Extends `sys.path` with each bundle's `code/` directory.
   - Imports the manifest-declared entry-point module(s). This
     triggers side-effect registration into the two seams described
     above (`neuromuscular_junction.py` native handler dict,
     `LogParserFactory.register(...)`).
   - Records one `NeuralModifierContribution` row per DB object the
     bundle's `modifier_data.json` loads.
3. Uninstall path:
   - Walk `NeuralModifier.iter_contributed_objects()` in install
     order, delete each target, then delete the contribution rows.
   - Remove the bundle directory from `neural_modifiers/`.
   - Flip status to `DISCOVERED` (or `BROKEN` on failure).
4. Tests cover install → enable → disable → uninstall and the
   `BROKEN` paths for hash mismatch and load failure.
5. Report.

### Task 7 — Documentation pass

1. Update `CLAUDE.md` fixtures section to reflect the four-tier
   layout and the `neuroplasticity` app.
2. Update `STYLE_GUIDE.md` fixtures section to match.
3. Rewrite docstrings in `neuroplasticity/models.py` to remove
   legacy "plugin" / "plugins_runtime" / "plugin_data.json"
   language in favor of `NeuralModifier` / `neural_modifiers/` /
   `modifier_data.json`.
4. Mark this file (`FIXTURE_SEPARATION_PROMPT.md`) complete /
   superseded by checking the acceptance criteria below.
5. Add `TASKS.md` Future entries: biopsy rebuild, modifier garden
   (3rd-party marketplace), immutability audit sweep.
6. Report.

---

## `core_dump` Replacement (Deferred — Post-Delivery)

The existing `common/management/commands/core_dump.py` is a blacklist-
based `dumpdata` wrapper. It is not aware of the four-tier layout or
of `NeuralModifierContribution` rows. Replacing it with a
tier-aware `biopsy` command is deferred to post-delivery. Task 5 is
hand-split, not tool-generated.

Planned biopsy methodology (for the TASKS.md Future entry):

- Preserve the `TRANSACTIONAL_MODELS` blacklist and add
  `neuroplasticity` to it.
- Model-level: integer PK → `genetic_immutables.json`. UUID PK →
  row-level classification.
- Row-level: any row that is a `NeuralModifierContribution` target is
  skipped (it belongs to a bundle, not core). A `ZYGOTE_ROWS` allowlist
  routes to `zygote.json`. Everything else routes to
  `initial_phenotypes.json`. `petri_dish.json` is never generated —
  it is hand-maintained.
- Emit a per-app / per-tier row-count summary at the end of the run.

---

## Acceptance Criteria

- [ ] Every app's `initial_data.json` is replaced by the appropriate
      subset of the four-tier files.
- [ ] No file named `initial_data.json` remains anywhere under
      `are-self-api/`.
- [ ] Every new UUID introduced during Pass 2 is a `uuid.uuid4()`
      random literal. No derivation schemes in `common/constants.py`
      or anywhere else.
- [ ] `python manage.py loaddata genetic_immutables.json` succeeds on
      a fresh database (via the explicit test-base-class paths, not
      the removed magic-name auto-discovery).
- [ ] Install script loads immutables → zygote → phenotypes in order,
      end-to-end on a fresh database.
- [ ] `CommonTestCase` loads only immutables.
- [ ] `CommonFixturesAPITestCase` loads immutables → zygote →
      petri_dish.
- [ ] The Unreal `NeuralModifier` lives at
      `neuroplasticity/modifier_genome/unreal/` with manifest,
      `modifier_data.json`, and scaffolded `code/`.
- [ ] `neural_modifiers/` is gitignored and the install path uses it
      at runtime.
- [ ] `./manage.py build_modifier unreal` produces an installable
      artifact.
- [ ] Loader walks `neural_modifiers/*/`, verifies hashes, imports
      entry points, records contributions, and the uninstall path
      rolls them back via `iter_contributed_objects()`.
- [ ] Both registration seams (native handler dict + `LogParserFactory`)
      pick up bundle registrations via side-effect imports.
- [ ] `ollama_fixture_generator.py` is deleted.
- [ ] `CLAUDE.md`, `STYLE_GUIDE.md`, and `neuroplasticity/models.py`
      docstrings use locked neuroplasticity vocabulary throughout.
- [ ] **All existing tests pass.** No regressions. No skips that
      weren't already skipped before Pass 2 started.
- [ ] `TASKS.md` has Future entries for biopsy rebuild, modifier
      garden, and immutability audit.

---

## Hazards

1. **`initial_data.json` auto-discovery is gone.** The old tuple
   `('initial_data.json',)` on `CommonTestCase` relied on Django's
   magic-name behavior. None of the new tier names are magic. Test
   base classes and the install script MUST list per-app paths
   explicitly.

2. **FK constraint ordering across tiers.** `loaddata` defers
   constraints within a single command. Keep each tier load as a
   single command that picks up every app's file for that tier so
   cross-app FKs resolve in one transaction.

3. **Hardcoded UUIDs in tests.** Search the test suite for hardcoded
   UUIDs before you move rows. Any test that hardcoded an old
   `initial_data.json` UUID literal needs updating to the new
   fixture's frozen literal.

4. **Model class UUID constants.** `Identity.THALAMUS`,
   `IdentityDisc.THALAMUS`, `ProjectEnvironment.DEFAULT_ENVIRONMENT`,
   and every `Effector.*` / `Executable.*` constant is referenced in
   production code. Their values are frozen. Fixtures must match them.

5. **Cross-file UUID references.** CNS rows reference environment and
   identity UUIDs. Environments rows reference context keys. When you
   move a row between tiers, every FK that pointed at it must be
   rewritten consistently in the same commit.

6. **M2M targets load first.** Any M2M target (e.g. `aimodel.roles`,
   `aimodel.capabilities`) must already be loaded before the row
   that references it. M2M targets are generally integer-PK
   vocabulary, so they belong in `genetic_immutables.json` — which
   loads first. Verify.

7. **Docstring drift in `neuroplasticity/models.py`.** Do not let
   the legacy "plugin" language bleed into any NEW code. Task 7
   cleans the existing occurrences.

8. **The install script is Windows-only.** A Python rewrite is a
   separate TASKS.md item. Pass 2 only edits the existing `.bat`.

---

If you get to the end of a task and you are not sure whether the
next step is in scope, stop and ask. If a task instruction appears
to contradict the ground rules at the top of this file, the ground
rules win — report the contradiction.
