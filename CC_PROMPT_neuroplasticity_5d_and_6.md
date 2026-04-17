# Claude Code prompt — are-self-api: Pass 2 Tasks 5d + 6 (Unreal modifier bundle + loader, with tests)

**Paste this into a fresh Claude Code session at the repo root of `are-self-api`, branch `uuid-migration`.**

This prompt covers **two staged commits** on top of the just-merged hypothalamus UUID propagation:

- **Commit A (Task 5d):** scaffold the first `NeuralModifier` bundle on disk — `neuroplasticity/modifier_genome/unreal/` — using the UE-flavored rows that Pass 2 Step 1 already held aside. Gitignore `/neural_modifiers/`. Drop the scratch `unreal_modifier.json` files now that their contents live in the bundle.
- **Commit B (Task 6):** wire `./manage.py build_modifier <slug>`, the contribution-aware loader, and install/enable/disable/uninstall lifecycle. Tests cover the happy path and both BROKEN paths (manifest hash mismatch, load failure).

Do them in that order — Commit A gives Commit B something real to load.

---

## Ground rules, up top

1. **Locked vocabulary — use it exactly.** See `TASKS.md` entry "UUID migration Pass 2". The words are:
   - app: `neuroplasticity`
   - DB model: `NeuralModifier` (Are-Self's word for a plugin bundle)
   - committed source tree: `neuroplasticity/modifier_genome/{slug}/`
   - runtime install tree (gitignored, at repo root): `neural_modifiers/{slug}/`
   - bundle payload filename: `modifier_data.json`
   - manifest filename: `manifest.json`
   - management command: `build_modifier`
   
   **The word "plugin" does not appear in any new code, filename, or docstring.** `neuroplasticity/models.py` docstrings still say "plugin / plugins_runtime / plugin_data.json" — that drift is Task 7's to fix and is **out of scope here**. Leave the existing docstrings alone. Just don't propagate that language anywhere new.

2. **No deterministic UUIDs. No uuid5. No namespaces.** Every new UUID you generate is `uuid.uuid4()`. Any UUID literal that already exists in a fixture stays verbatim — do not re-derive. The model table is the namespace, full stop. (If you catch yourself typing `uuid.uuid5`, `NAMESPACE_DNS`, or `deterministic` anywhere, stop and delete.)

3. **Do NOT delete or restructure the `initial_data.json` files.** Michael's explicit instruction this round: leave the legacy per-app `initial_data.json` alone until the UE modifier is wired end-to-end. The tier files (`genetic_immutables.json` / `zygote.json` / `initial_phenotypes.json` / `unreal_modifier.json` / `petri_dish.json`) already coexist with them; that's fine for now.

4. **Do NOT touch `are-self-install.bat`.** Michael updated it by hand last round (9-step installer, loads `genetic_immutables.json` → `zygote.json` → `initial_phenotypes.json` at step 8). Wiring bundle install into that script is a later call — flag it as a follow-up in your commit message / TASKS entry, but don't edit the .bat.

5. **Commit style.** Two commits, bisectable. Commit A is pure file moves + scaffolding + gitignore. Commit B is code + tests. Each commit's tests should be green independently.

---

## What exists on disk right now

### `neuroplasticity/models.py` — the registry contract

Five models, already migrated, already have a working initial migration at `neuroplasticity/migrations/0001_initial.py`. You're building against this contract, not modifying it:

- **`NeuralModifierStatus`** — NameMixin lookup. Constants: `DISCOVERED=1`, `INSTALLED=2`, `ENABLED=3`, `DISABLED=4`, `BROKEN=5`. Integer PKs. State machine: `DISCOVERED → INSTALLED → ENABLED ↔ DISABLED`, all with side transitions to `BROKEN`.
- **`NeuralModifier`** — one row per bundle. Fields: `status` (FK), `slug` (unique), `version`, `author`, `license`, `manifest_hash`, `manifest_json` (JSON cache). DefaultFieldsMixin gives it `name`, `created`, `modified`. Never deleted on uninstall — status flips to `DISCOVERED`.
- **`NeuralModifierContribution`** — generic FK (`content_type`, `object_id` UUIDField, `content_object`) back to whichever DB object a bundle created. One row per contributed object. This is the uninstall manifest in table form.
- **`NeuralModifierInstallationLog`** — one row per install attempt. `installation_manifest` JSONField freezes the manifest at that moment.
- **`NeuralModifierInstallationEventType`** — NameMixin lookup. Constants: `INSTALL=1`, `UNINSTALL=2`, `ENABLE=3`, `DISABLE=4`, `LOAD_FAILED=5`, `HASH_MISMATCH=6`.
- **`NeuralModifierInstallationEvent`** — append-only per-step log under an InstallationLog.

Reference methods already on the model:
- `NeuralModifier.current_installation()` — most-recent log, for uninstall replay.
- `NeuralModifier.iter_contributed_objects()` — yields live DB objects in install order, silently skipping orphans.

**The status / event-type fixture rows need to exist before anything here runs.** Check whether `neuroplasticity/fixtures/reference_data.json` (or its eventual rename `genetic_immutables.json` per Task 5a — not done yet) already has the 5 status rows and the 6 event-type rows. If not, add them as part of Commit B and load them in the relevant test setUp. These 11 rows are genetic immutables with integer PKs; they do **not** go into any modifier bundle.

### Held-aside UE rows from Step 1 — your bundle payload

The Step 1 completion pass (see `STEP1_COMPLETE_REPORT.md` §5) wrote two scratch files:

- `central_nervous_system/fixtures/unreal_modifier.json` — 198 rows (13 UE NeuralPathways + `Corpus Callosum` + their Neurons, Axons, NeuronContexts, EffectorContexts, EAAs, Effectors that are exclusively UE).
- `environments/fixtures/unreal_modifier.json` — 65 rows (6 UE Executables, UE Default Environment, UE ContextVariables, UE ExecutableArguments).

**263 rows total.** These are your `modifier_data.json` payload. The report flags a handful of known smells (§6.4 `Corpus Callosum`, §7.6 `Deploy`/`RecordPSOs` empty-shell pathways) — **don't try to resolve them here**. Preserve the rows verbatim. Those are future review items.

### What got deleted already

- `hypothalamus/parsing_tools/ollama_fixture_generator.py` — deleted by the hypothalamus UUID commit `1e98e303`. You don't need to re-delete it. If `TASKS.md` Task 5d still mentions "Delete `ollama_fixture_generator.py`" in the bullet, note in your commit message that this sub-step was already done upstream.
- Legacy `deploy_release_test` Executable (`5fbd152c-...`) — already dropped from the tier split per `STEP1_COMPLETE_REPORT.md` §2. Do not re-introduce it anywhere. Do not include it in the bundle.

### What does NOT exist yet

- `neuroplasticity/modifier_genome/` directory — you're creating it.
- `neural_modifiers/` directory at repo root — you'll add a gitignore entry. At runtime, `build_modifier` creates `neural_modifiers/{slug}/`. It does not need to exist in the repo.
- `build_modifier` management command — Commit B.
- `neuroplasticity/loader.py` (or wherever the loader code lands) — Commit B.

---

## Commit A — Task 5d scaffolding

Goal: stand up `neuroplasticity/modifier_genome/unreal/` with every file it needs, move the held-aside rows in, drop the scratch files, and close the gitignore loop. No Python code runs yet. No tests yet.

### A.1 — Directory layout

```
neuroplasticity/
├── modifier_genome/
│   ├── .gitkeep
│   └── unreal/
│       ├── manifest.json
│       ├── modifier_data.json
│       ├── README.md
│       └── code/
│           ├── __init__.py
│           └── are_self_unreal/
│               ├── __init__.py
│               ├── handlers.py
│               └── log_parsers.py
```

Rationale for the `code/are_self_unreal/` sub-package: the loader adds each bundle's `code/` to `sys.path`, so the importable top-level name needs to be unique across bundles to prevent cross-bundle collision. Namespacing with `are_self_{slug}` is the simplest convention. If you pick a different convention, document it in the bundle's README.

### A.2 — `manifest.json` contents

Minimum viable schema. JSON, sorted keys, 2-space indent, trailing newline. Treat it as the source of truth the DB row mirrors.

```json
{
  "slug": "unreal",
  "name": "Unreal Engine",
  "version": "1.0.0",
  "author": "Are-Self Team",
  "license": "MIT",
  "description": "Unreal Engine 5 build, staging, and release pathways for Are-Self. Ships the UE Executable set, the UE Default Environment, the 14 UE-named NeuralPathways (Full / Deploy / Stage / RecordPSOs / Compile Shaders / ...) with their neuron + axon + effector closure, and the log-parser strategies needed to read UE log output.",
  "entry_modules": ["are_self_unreal"],
  "requires_are_self": ">=0.1.0"
}
```

- `slug` — matches the directory name and `NeuralModifier.slug`. Stable identifier.
- `entry_modules` — list of Python module names the loader will `importlib.import_module(name)` after extending `sys.path`. Side-effect registration (native handlers, log parser strategies) happens at import time inside these modules.
- `requires_are_self` — PEP 440-style version constraint. Enforced softly for now (log a warning on mismatch; don't refuse to load).

### A.3 — `modifier_data.json` contents

Merge the two scratch files — `central_nervous_system/fixtures/unreal_modifier.json` (198 rows) and `environments/fixtures/unreal_modifier.json` (65 rows) — into a single `neuroplasticity/modifier_genome/unreal/modifier_data.json` of 263 rows.

Rules:

- Preserve every row verbatim — pks, field values, JSON key order inside fields, everything. The loader will call `loaddata` (or equivalent) against this file.
- Concatenate in **environments-first, CNS-second** order so that if you ever run a dumbed-down straight-through load without bundle machinery, environment rows (which CNS FKs into) land first.
- Write with `json.dump(..., indent=2, sort_keys=False)` and an explicit trailing `'\n'`. Don't reformat the inner dicts.
- SHA-256 the resulting file and log that hash in your commit message — future audits will want to detect drift.

After writing `modifier_data.json`, **delete**:
- `central_nervous_system/fixtures/unreal_modifier.json`
- `environments/fixtures/unreal_modifier.json`
- their counterparts in `.step1_backup/` if any exist (keep `.step1_backup/` itself around — it's Michael's audit trail)

Double-check: grep the repo for any remaining references to those deleted paths, particularly in test fixtures lists and `CommonTestCase` per-app fixture paths. There shouldn't be any — these files were staged but never referenced by test machinery — but confirm.

### A.4 — `code/are_self_unreal/` stubs

The actual UE handlers and UE log-parser strategies are not written yet (that's downstream work, and deliberately out of scope here — we're scaffolding the shape). For Commit A the three code files are placeholders with module docstrings and no-op import-time side effects:

**`code/__init__.py`** — empty. Marks the directory as a package root for `sys.path` purposes. (Technically optional since we're treating `code/` as a path, not a package, but leave it in for cleanliness.)

**`code/are_self_unreal/__init__.py`** —

```python
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
```

**`code/are_self_unreal/handlers.py`** —

```python
"""Placeholder for Unreal Engine native handlers.

When populated, this module imports the NMJ native-handler registry from
central_nervous_system.neuromuscular_junction and registers UE-specific
handlers (UNREAL_CMD, UNREAL_AUTOMATION_TOOL, UNREAL_STAGING,
UNREAL_RELEASE_TEST, UNREAL_SHADER_TOOL, VERSION_HANDLER) against it.

Currently a no-op so the bundle loads cleanly. The actual handler
implementations migrate in a follow-up pass once the bundle pipeline
is proven.
"""
```

**`code/are_self_unreal/log_parsers.py`** —

```python
"""Placeholder for Unreal Engine log parser strategies.

When populated, this module imports LogParserFactory from
occipital_lobe.log_parser and calls LogParserFactory.register(...) for
each UE log variant recognized by ue_tools. Registration is idempotent
and safe to re-run.

Currently a no-op so the bundle loads cleanly.
"""
```

These stubs make Commit B's "import entry modules" step succeed. They're meant to be fleshed out later without changing the bundle shape.

### A.5 — `README.md`

Short. Who this bundle is for, what it ships, how to install/uninstall. 20–40 lines. Plain prose, no bullets for the sake of bullets.

### A.6 — `modifier_genome/.gitkeep`

One empty file so git tracks the directory when no other bundles exist.

### A.7 — `.gitignore` entry

Add to the repo-root `.gitignore`:

```
# --- Neuroplasticity runtime ---
/neural_modifiers/
```

Position it near the existing Python / Django sections. Leading `/` anchors it to the repo root — subdirectory matches elsewhere (if any) stay ignored by the general rules.

### A.8 — `CLAUDE.md` / `TASKS.md` touch-up

- In `TASKS.md`, mark Task 5d bullet as complete (the one under "UUID migration Pass 2 — fixture tier split").
- Note that `ollama_fixture_generator.py` deletion was handled by the hypothalamus UUID commit — no additional work needed for that sub-step.
- Leave `install.bat` follow-up flagged but unchanged.

### A.9 — Commit A checklist

- [ ] `neuroplasticity/modifier_genome/unreal/` exists with manifest.json, modifier_data.json (263 rows), README.md, and code/ tree.
- [ ] `modifier_genome/.gitkeep` exists.
- [ ] `central_nervous_system/fixtures/unreal_modifier.json` and `environments/fixtures/unreal_modifier.json` deleted.
- [ ] `/neural_modifiers/` entry added to `.gitignore`.
- [ ] `grep -rn "unreal_modifier.json" .` returns zero references outside `STEP1_COMPLETE_REPORT.md`, the new bundle, and `.step1_backup/`.
- [ ] `TASKS.md` Task 5d bullet marked done.
- [ ] `python manage.py test neuroplasticity` passes (even though there's nothing new to test — confirms existing Pass 1 tests still green).
- [ ] Commit message includes the SHA-256 of `modifier_data.json` and a sentence noting that `ollama_fixture_generator.py` deletion was pre-handled by the hypothalamus UUID propagation commit.

---

## Commit B — Task 6 build_modifier + loader + tests

Goal: make the scaffolded bundle actually installable and uninstallable via `./manage.py`, with contribution tracking and the two BROKEN paths covered by tests.

### B.1 — `./manage.py build_modifier <slug>` (and siblings)

Design the CLI surface to cover the full lifecycle. One management command file per verb is fine (`neuroplasticity/management/commands/build_modifier.py` etc.), or a single dispatcher with subcommands — CC's call.

Expected surface:

```
./manage.py build_modifier <slug>
    # Copy neuroplasticity/modifier_genome/<slug>/ to neural_modifiers/<slug>/,
    # compute manifest_hash, create or find the NeuralModifier row, then run the
    # full install pipeline (validate manifest, extend sys.path, import entry
    # modules, load modifier_data.json with contribution tracking, set INSTALLED).
    # Idempotent: re-running on an already-installed bundle with matching hash
    # is a no-op; hash drift flips BROKEN.

./manage.py enable_modifier <slug>
    # Flip INSTALLED → ENABLED. Emits an ENABLE event.

./manage.py disable_modifier <slug>
    # Flip ENABLED → DISABLED. Emits a DISABLE event. Code stays on sys.path,
    # contributions stay in DB.

./manage.py uninstall_modifier <slug>
    # Walk NeuralModifier.iter_contributed_objects() in install order, delete
    # each target, delete the contribution rows, remove neural_modifiers/<slug>/
    # from disk, flip NeuralModifier.status to DISCOVERED, emit UNINSTALL event.

./manage.py list_modifiers
    # Read-only: prints slug, status, version, contribution count, last install
    # timestamp. One line per modifier. Useful for smoke/debug.
```

Keep the `enable_modifier` / `disable_modifier` / `list_modifiers` commands thin — they mostly just flip a status FK or dump the table. The real meat is in `build_modifier` and `uninstall_modifier`.

### B.2 — The loader (`neuroplasticity/loader.py`)

This is the pure-Python library the management commands call into. Keep it CLI-agnostic so future API/UI surfaces can reuse it.

Suggested public API:

```python
def install_bundle(slug: str) -> NeuralModifier: ...
def uninstall_bundle(slug: str) -> NeuralModifier: ...
def enable_bundle(slug: str) -> NeuralModifier: ...
def disable_bundle(slug: str) -> NeuralModifier: ...
def iter_installed_bundles() -> Iterable[NeuralModifier]: ...
def boot_bundles() -> None:
    """Called on Django startup (AppConfig.ready). Iterates every
    `neural_modifiers/*/` directory, validates manifest_hash against the
    NeuralModifier row, extends sys.path, imports entry modules for any bundle
    whose status is INSTALLED or ENABLED. Flips BROKEN on hash drift or import
    failure. Does NOT load modifier_data.json — that already happened at
    install time; boot is just about putting code on sys.path."""
```

`install_bundle` flow (all wrapped in `transaction.atomic()`):

1. Resolve source path: `neuroplasticity/modifier_genome/<slug>/`. If missing, raise — nothing to install.
2. Read `manifest.json` from source, validate minimum schema (slug, version, author, license, entry_modules). Compute `manifest_hash = sha256(manifest.json bytes).hexdigest()`.
3. Open a new `NeuralModifierInstallationLog` against the `NeuralModifier` row (create the row if this is first install; slug is unique).
4. Copy `modifier_genome/<slug>/` to `neural_modifiers/<slug>/`. Use `shutil.copytree` with `dirs_exist_ok=False` — a pre-existing runtime dir is an error (caller should uninstall first). Log a `INSTALL` event with the file list.
5. Extend `sys.path` with `neural_modifiers/<slug>/code/` (insert at index 0 so bundle code shadows anything of the same name elsewhere — though bundle namespacing should prevent collisions).
6. `importlib.import_module(name)` for each name in `entry_modules`. On `ImportError` or any exception, log a `LOAD_FAILED` event with the traceback, flip status to `BROKEN`, re-raise.
7. Read `modifier_data.json`, pipe it through `django.core.management.call_command('loaddata', ...)` OR use the `Deserializer` directly — **whichever approach lets you capture the list of newly-created DB object (content_type, object_id) pairs** for contribution tracking. `loaddata` won't surface that by default, so the Deserializer-direct approach is probably cleaner.
8. For each deserialized object: `obj.save()`, then `NeuralModifierContribution.objects.create(neural_modifier=..., content_type=..., object_id=obj.pk)`. One row per DB object created.
9. Set `NeuralModifier.manifest_hash`, `manifest_json`, `version`, etc., from the manifest. Flip status to `INSTALLED`. Log a final success event on the InstallationLog.

`uninstall_bundle` flow (also atomic):

1. Fetch the `NeuralModifier` row by slug. Open a new InstallationLog — yes, even uninstalls get one; the `installation_manifest` field freezes whatever manifest we're rolling back from.
2. Walk `nm.iter_contributed_objects()`. For each live target: delete it. Count orphans for the event payload.
3. Delete all `NeuralModifierContribution` rows for this modifier.
4. Prune `sys.path` — remove the bundle's `code/` entry if present.
5. `shutil.rmtree('neural_modifiers/<slug>/')`.
6. Flip status to `DISCOVERED`.
7. Log a `UNINSTALL` event with target count + orphan count.

### B.3 — Side-effect registration surface — just document it

You don't need to actually wire handlers or log parsers in Commit B. The two registration targets exist but are empty:

- `central_nervous_system/neuromuscular_junction.py` — the native-handler dict. Bundles will mutate this at import time.
- `occipital_lobe/log_parser.py` — `LogParserFactory.register(...)` calls live here. Already used by `ue_tools/log_parser.py` per Task 4.

The Unreal bundle's `handlers.py` / `log_parsers.py` are deliberate no-ops for now (see A.4). The loader's job is just to import them — what they register is their problem, and the bundle's.

If you spot that `neuromuscular_junction.py` doesn't yet have a handler-registry pattern, note it in the commit message as a follow-up but **do not design it here** — that's a separate task with its own review surface.

### B.4 — `AppConfig.ready()` boot hook

Wire `neuroplasticity/apps.py::NeuroplasticityConfig.ready()` to call `loader.boot_bundles()` after the apps registry is loaded. Guard with a `settings.DEBUG`/`sys.argv` check so `migrate` and test setup don't blow up trying to load bundles before the DB is ready — easiest gate: skip if the `neuralmodifier` table doesn't exist yet (catch `OperationalError` / `ProgrammingError`).

`boot_bundles()` is lightweight: hash-check + sys.path + entry-module import. It does NOT re-run `loaddata`. That only happens in `install_bundle`.

### B.5 — Tests

Target: `neuroplasticity/tests/test_modifier_lifecycle.py` (split the existing scaffold `neuroplasticity/tests.py` into a tests package if it's easier, or just replace the stub).

Use a **tmp_path + settings override** pattern so tests don't touch the real `neural_modifiers/` or `modifier_genome/` directories. Parameterize `MODIFIER_GENOME_ROOT` and `NEURAL_MODIFIERS_ROOT` in settings.py so tests can override them via `override_settings`. In production they default to `BASE_DIR / 'neuroplasticity/modifier_genome'` and `BASE_DIR / 'neural_modifiers'`.

Provide a **`build_fake_bundle(tmp_path, slug, *, modifier_data=None, entry_modules=("are_self_fake",), with_broken_import=False) -> Path`** test helper that writes a valid-shape fake bundle into `tmp_path/modifier_genome/<slug>/`. Let tests construct minimum-viable fixtures (e.g. an `IdentityAddonPhase` row or some other cheap UUIDable model — avoid depending on the real 263-row UE bundle for unit tests).

Required test coverage (8 tests minimum):

1. **`test_install_happy_path`** — install a 3-row fake bundle; assert `NeuralModifier.status == INSTALLED`, 3 contribution rows exist, entry module import triggered, `neural_modifiers/<slug>/` exists on disk, `InstallationLog` + `INSTALL` event recorded.
2. **`test_enable_disable_round_trip`** — install, enable, disable, re-enable; verify status transitions + event trail.
3. **`test_uninstall_full_rollback`** — install a 3-row bundle, uninstall; assert all 3 target objects gone, 0 contribution rows, `neural_modifiers/<slug>/` removed, NeuralModifier row still exists with status DISCOVERED, `UNINSTALL` event recorded.
4. **`test_uninstall_handles_orphaned_contribution`** — install a 3-row bundle, manually delete one target out-of-band, uninstall; assert no crash, orphan counted in event payload, status still flips to DISCOVERED.
5. **`test_install_rejects_hash_drift`** — install; mutate `neural_modifiers/<slug>/manifest.json` on disk so the hash diverges from `NeuralModifier.manifest_hash`; call `boot_bundles()`; assert status flipped to BROKEN, `HASH_MISMATCH` event recorded, entry module NOT imported.
6. **`test_install_rejects_bad_import`** — build_fake_bundle with `with_broken_import=True` (entry module raises `ImportError` at import time); install; assert status BROKEN, `LOAD_FAILED` event recorded with traceback payload, transaction rolled back (no contribution rows, no copied runtime dir, no InstallationLog left in a success state).
7. **`test_reinstall_creates_new_log`** — install, uninstall, reinstall same slug; assert NeuralModifier row reused (same PK), two InstallationLog rows exist (order by `-created`), `current_installation()` returns the latest.
8. **`test_list_modifiers_reports_status`** — install two bundles with different statuses; capture stdout from `call_command('list_modifiers')`; assert both slugs + statuses appear.

Additional coverage worth adding if time permits:

- `test_install_is_idempotent` — re-run `build_modifier` on an already-INSTALLED bundle with matching hash; assert no-op (no new contributions, no new InstallationLog, status unchanged). Nudge toward this via a `--force` flag if idempotency turns out to be painful — either works, document the choice.
- `test_boot_bundles_skips_missing_table` — simulate pre-migrate state (mock the ORM to raise `OperationalError` on first query); assert `boot_bundles()` returns cleanly without propagating.

### B.6 — `CLAUDE.md` / `TASKS.md` touch-up

- In `TASKS.md`, mark Task 6 bullet as complete.
- Add a one-line entry under "## Completed —" section with date + commit-SHA placeholder ("Pass 2 Task 6 — NeuralModifier build/install/uninstall + contribution-aware loader + 8 tests (pending: real UE handler registration, install.bat wiring)").
- Flag two follow-ups in "## Top Priority" or "## Next Up":
  - **Wire `are-self-install.bat` to call `./manage.py build_modifier unreal` post-migrate** (after step 8 fixture loads). Michael will probably do this by hand.
  - **Fill in the UE bundle's real handler/log-parser registrations.** The scaffolded `code/are_self_unreal/handlers.py` and `log_parsers.py` are no-op stubs.

### B.7 — Commit B checklist

- [ ] `./manage.py build_modifier unreal` on a fresh DB (genetic_immutables + zygote + initial_phenotypes + the 11 neuroplasticity status/event-type rows loaded) succeeds. Creates 263 contribution rows. Status INSTALLED.
- [ ] `./manage.py uninstall_modifier unreal` on that state rolls all 263 rows back and wipes `neural_modifiers/unreal/`. Status DISCOVERED.
- [ ] `./manage.py enable_modifier unreal`, `./manage.py disable_modifier unreal` flip status with event trails.
- [ ] `./manage.py list_modifiers` prints at least one line per installed bundle.
- [ ] `python manage.py test neuroplasticity` — 8+ tests, all green.
- [ ] Full suite `python manage.py test` still green (no regression in CNS / hypothalamus / environments from the bundle load).
- [ ] `grep -rn "plugin" neuroplasticity/loader.py neuroplasticity/management/` returns zero hits. Language stays NeuralModifier-flavored.
- [ ] `INSTALLED_APPS` has NOT been mutated by any code path. `grep -rn "INSTALLED_APPS" neuroplasticity/` returns hits only in config files and docstrings, never in runtime loader code.
- [ ] `TASKS.md` Task 6 bullet marked done. Two follow-ups recorded.

---

## Scope boundaries

**In scope:**
- File scaffolding (Commit A).
- `build_modifier` + lifecycle commands + loader + 8 tests (Commit B).
- Documentation touch-up in `TASKS.md`.

**Out of scope:**
- Renaming `neuroplasticity/fixtures/reference_data.json` → `genetic_immutables.json` (that's Task 5a; it's a separate no-op rename and can land on its own).
- Updating `neuroplasticity/models.py` docstrings from "plugin" language to "NeuralModifier" language (that's Task 7).
- Wiring real UE native handlers or log parser strategies (follow-up after the bundle pipeline proves out).
- Editing `are-self-install.bat` to run `build_modifier unreal` at install time (Michael-call).
- Touching `initial_data.json` files or collapsing the tier-split into them (deferred — Michael's explicit call this round).
- Resolving the known data smells in `STEP1_COMPLETE_REPORT.md` §6.1–6.5 (e.g. `qwen3-coder:30b` missing provider row, dangling `aimodelselectionfilter` FK fields, `Corpus Callosum` environment smell). Not blocking for bundle mechanics.
- Designing a `NeuralModifier` publication / signing / garden format (TASKS.md "Modifier Garden" entry — later).

---

## If something blocks you

- **Test DB doesn't have the 11 neuroplasticity status + event-type rows.** Add a `neuroplasticity/fixtures/genetic_immutables.json` (or extend `reference_data.json` if it exists) with all 11 rows. Load it in the test suite's base setUp. If the rename is happening under Task 5a separately, drop the rows into whichever filename exists today.
- **`loaddata` doesn't return created-object identifiers.** Switch to `django.core.serializers.python.Deserializer` — it yields `DeserializedObject` instances whose `.object` is the model instance, and you can iterate them before or after `.save()` to collect `(ContentType, pk)` pairs.
- **`boot_bundles()` blows up on first migrate.** Wrap the first ORM call in try/except `(OperationalError, ProgrammingError)` and return silently; that's the "DB not ready" case. Log at DEBUG, not WARNING.
- **You find `plugin` still in neuroplasticity code paths.** Don't chase it. Note the file + line in your commit message as a Task 7 follow-up. The rename is out of scope here.
- **You find yourself touching `are-self-install.bat`.** Stop. Don't. Michael owns that file right now.
- **You find yourself adding `uuid5` or `NAMESPACE_DNS`.** Stop. Delete. Use `uuid.uuid4()`.

---

## Expected scope

Commit A: 30–60 min (mostly file moves + gitignore + README). Commit B: 2–4 hours if the Deserializer path is clean, maybe longer if test fixtures are fiddly. The 8-test lifecycle suite is the biggest single chunk.

Make each commit green on its own. If Commit B runs long, ship Commit A by itself — scaffolding without the loader is still a useful checkpoint.

---

End of prompt.
