# NeuralModifier Completion Plan

> **Scope.** What it takes to declare the NeuralModifier feature area
> feature-complete, starting from the April 18, 2026 state of the
> `uuid-migration` branch (commits `bf2e11d` Task 5d scaffold + `15ceb37`
> Task 6 lifecycle landed, 9 lifecycle tests passing). Supersedes
> `FIXTURE_SEPARATION_PROMPT.md`, the various `CC_PROMPT_*.md` files,
> `STEP1_REPORT.md`, `STEP1_COMPLETE_REPORT.md`, and
> `UUID_MIGRATION_PROMPT.md` — all nuked April 18 because their work
> landed. When this plan is done, this file gets nuked too.

## Ground rules (carry forward from prior passes)

1. **Vocabulary is locked.** App is `neuroplasticity`. Installable
   bundles are `NeuralModifier`s. **Committed archives** live at
   `neuroplasticity/genomes/<slug>.zip` — the zip IS the bundle; there
   is no unzipped source tree. Runtime install tree:
   `neuroplasticity/grafts/<slug>/` (gitignored). Transient scratch:
   `neuroplasticity/operating_room/` (gitignored; empty between
   operations). Bundle payload file is `modifier_data.json` inside the
   zip. Single public install API: `loader.install_bundle_from_archive(path)`
   (UI route: `POST /api/v2/neural-modifiers/catalog/<slug>/install/`).
   **Never** use the word "plugin" in new code, docstrings, or commit
   messages.
2. **UUIDs are `uuid.uuid4()` random literals.** No namespaces, no
   derivation seeds, no deterministic schemes. Existing UUID literals in
   fixtures or the modifier's frozen source are opaque frozen values.
3. **`INSTALLED_APPS` is never mutated at runtime.** Contributions are
   data. The loader extends `sys.path`, imports entry modules, and
   records `NeuralModifierContribution` rows — it does not touch
   Django's app registry.
4. **Michael removes files.** Claude proposes, Michael deletes. Never
   suggest removing `initial_data.json` or any user-authored artifact.
5. **`are-self-install.bat` stays lean.** Install goes:
   `genetic_immutables` → `zygote` → `initial_phenotypes`. NeuralModifier
   installs happen through the modifier-garden UI, **not** through
   `install.bat`.

## Where we stand

**Most recent landing — NeuralModifier layout consolidation + install/uninstall
bug fixes (2026-04-20):** Three sibling root-level dirs collapsed into
`neuroplasticity/genomes/` (committed zips), `neuroplasticity/grafts/`
(runtime, gitignored), and `neuroplasticity/operating_room/` (transient,
gitignored, empty between ops). Source tree at `modifier_genome/`
deleted — the zip is the single source of truth. Settings renamed:
`MODIFIER_GENOME_ROOT` retired, `NEURAL_MODIFIERS_ROOT` →
`NEURAL_MODIFIER_GRAFTS_ROOT`, `NEURAL_MODIFIER_CATALOG_ROOT` →
`NEURAL_MODIFIER_GENOMES_ROOT`, new `NEURAL_MODIFIER_OPERATING_ROOM_ROOT`.
`build_modifier` / `pack_modifier` retired. Uninstall now DELETES the
`NeuralModifier` row (AVAILABLE = zip exists + no DB row) — contributions,
logs, events cascade. Staging leak (`_staging/`) fixed via
`tempfile.mkdtemp(dir=operating_room_root())` + `try/finally`.
FileExistsError pre-flight moved BEFORE DB writes so a collision no
longer leaks a bogus row. Failed fresh install deletes the row it
created — no BROKEN/DISCOVERED stubs survive. API uninstall returns
`{slug, uninstalled: true}` and broadcasts slug-only Acetylcholine.
Unreal bundle round-trip test rehomed to
`neuroplasticity/tests/test_install_unreal_bundle.py`, exercising
`install_bundle_from_archive` against `genomes/unreal.zip`.

**Landed:**

- `neuroplasticity/models.py` — `NeuralModifier`, `NeuralModifierStatus`,
  `NeuralModifierContribution` (GFK + `UUIDField` object_id),
  `NeuralModifierInstallationLog`, `NeuralModifierInstallationEvent`,
  `NeuralModifierInstallationEventType`.
- `neuroplasticity/loader.py` (422 lines) — contribution-aware loader:
  walks `neural_modifiers/*/`, verifies `manifest_hash`, extends
  `sys.path`, imports entry modules, records contributions via a
  wrapped `Deserializer`.
- Management commands: `build_modifier`, `enable_modifier`,
  `disable_modifier`, `uninstall_modifier`, `list_modifiers`.
- `neuroplasticity/apps.py` boot hook — on ready, calls the loader and
  flips mismatched bundles to `BROKEN`.
- `tests/test_modifier_lifecycle.py` — 9 tests, all green, covering
  install / uninstall / BROKEN paths.
- `neuroplasticity/modifier_genome/unreal/` — committed scaffold
  (`manifest.json` stub, empty `modifier_data.json`, `code/` dir,
  `README.md`).
- **Bundle-time registration surfaces (April 18):**
  `register_parietal_tool` / `unregister_parietal_tool` in
  `parietal_lobe/parietal_mcp/gateway.py` — module-level
  `_PARIETAL_TOOL_REGISTRY` is consulted first in
  `ParietalMCP.execute()`; on miss, the pre-existing dynamic-import
  path runs unchanged. `register_native_handler` /
  `unregister_native_handler` in
  `central_nervous_system/effectors/effector_casters/neuromuscular_junction.py`
  — operates on the existing `NATIVE_HANDLERS` dict; collisions
  against core or prior-bundle slugs raise `RuntimeError`; unregister
  is idempotent. 12 new tests
  (`parietal_lobe/parietal_mcp/tests/test_tool_registration.py`
  7 cases + `central_nervous_system/effectors/effector_casters/tests/test_native_handler_registration.py`
  5 cases) with `setUp`/`tearDown` snapshotting.
- **Task 9 — `update_version_metadata` moved into the bundle:**
  handler definition lives at
  `neuroplasticity/modifier_genome/unreal/code/are_self_unreal/version_metadata_handler.py`
  and is registered through `register_native_handler` from the bundle's
  entry module. Core `neuromuscular_junction.py` no longer defines or
  imports the handler. Unregister-then-register pattern inside
  `handlers.py` keeps re-imports on every `boot_bundles()` pass idempotent.
- **Task 10 — Unreal log parsers moved into the bundle:**
  `UEBuildLogStrategy` and `UERunLogStrategy` live at
  `neuroplasticity/modifier_genome/unreal/code/are_self_unreal/log_parsers.py`
  and register through `LogParserFactory.register` at import time. Core
  `occipital_lobe/log_parser.py` keeps the factory + the generic
  base; Unreal-specific strategies no longer live in core.
- **Task 13 — Parietal tool-set gating on NeuralModifier state (April 19):**
  `_fetch_tools` in `parietal_lobe/parietal_lobe.py` now excludes any
  `ToolDefinition` whose `NeuralModifierContribution` points at a
  bundle not in `ENABLED` state, via an `Exists(...)` subquery. Core
  tools (no contribution row) pass through untouched. Filter sits at
  the query layer, so every new `ParietalLobe` construction (once per
  `ReasoningSession`) picks up the current state — no cache layer to
  invalidate, lifecycle commands stay uninvolved. 5 integration tests
  in `parietal_lobe/tests/test_modifier_tool_gating.py` covering
  ENABLED (included), INSTALLED / DISABLED / BROKEN (excluded), and
  the ENABLED↔DISABLED round-trip that proves state flips land on the
  next session. Also in this pass: `neuroplasticity/fixtures/reference_data.json`
  → `genetic_immutables.json`, wired into `CommonTestCase.fixtures` so
  it auto-loads for every suite (was off-convention, only neuroplasticity
  app not following the four-tier layout).
- **Task 14 — Bundle-author documentation (April 19):**
  New `neuroplasticity/modifier_genome/README.md` covering directory
  layout, manifest schema (required keys + SHA-256 hash behavior),
  `modifier_data.json` contribution format (Django serialized rows,
  `uuid.uuid4()` PK rule, ordering + no cross-bundle FK rules),
  entry-module conventions for the three registration surfaces
  (`register_native_handler`, `register_parietal_tool`,
  `LogParserFactory.register`) with the unregister-then-register
  idempotency pattern, the full `build_modifier` / `enable_modifier`
  / `disable_modifier` / `uninstall_modifier` / `list_modifiers`
  lifecycle from the author's perspective, a ToolDefinition-gating
  callout pointing back at Task 13, an end-to-end authoring checklist,
  and the Unreal bundle pointer as the reference implementation.

**Not landed (this plan):**

The four work items below. Priority order is top-down — each item is
useful on its own and each later item assumes the earlier ones are in.

> **Next up: Task 8 verification.** The E2E protocol in
> `UNREAL_E2E_HANDOFF.md` is the acceptance test. Everything else in
> this plan is blocked on that passing — not because the code depends
> on it, but because without a clean round-trip we don't know whether
> the rest of the work is building on solid ground.

---

## April 19 design rulings — Modifier Garden state machine (Surface 1)

> **Context.** Dogfooding the garden against the Unreal bundle surfaced
> two UX failures and one correctness bug. (a) Installing a bundle
> required a dev shell (`loader.install_bundle('unreal')`) because no
> discovery path existed — the garden was blind to anything committed
> at `modifier_genome/<slug>/`. (b) After uninstall, rows flipped to
> `DISCOVERED` but the page has no per-row Install button, only a
> disabled Enable with tooltip "Install or repair first." Dead-end UX —
> a 10-year-old cannot recover. (c) The Task 12 uninstall-event
> `orphaned_ids` payload conflates "target was cascade-deleted in the
> same `atomic`" with "target was deleted out-of-band": 53/260 UUIDs
> surfaced as "orphans" after a clean uninstall when in fact the DB was
> empty. These three failures force a redesign of the modifier garden
> state machine. Michael's rulings below are locked.

**Q1 — Catalog format: zip files.** NeuralModifier bundles ship and
live on disk as `.zip` archives. A bundle is "in the catalog" iff its
zip file exists under the catalog root (directory TBD — probably
`neural_modifier_catalog/` at repo root, gitignored; committed
reference bundles at `modifier_genome/<slug>/` can be zipped into it at
build time). Manifest is read out of the zip **without full extraction**
using `zipfile.ZipFile` + `.read('manifest.json')`.

**Q2 — Install mechanics: unzip → install → nuke extraction.** Install
is: unzip the archive into a tempdir → run the existing
`install_bundle` codepath against the extraction → delete the
extraction tempdir. The zip stays on disk. The DB row (`NeuralModifier`
+ `NeuralModifierContribution`s) carries the live state. Uninstall
removes the DB row. Delete-modifier (new) removes the zip file. No
two-copies problem: the extraction is transient.

**Q3 — Install lands in `INSTALLED` (disabled), not auto-enabled.**
"Install" and "enable" are two distinct user actions. After install the
bundle's rows exist in the DB and its contributions are tracked, but
its tools / handlers / log parsers are gated off until the user flips
the Enable toggle. This matches the existing Task 13 gating — ENABLED
contributions are exposed; INSTALLED/DISABLED/BROKEN are not.

**Q4 — State machine.**

| State       | Zip on disk? | DB row?     | Contributions live? | Transitions out                      |
|-------------|--------------|-------------|---------------------|--------------------------------------|
| `AVAILABLE` | yes          | no          | no                  | Install → `INSTALLED`                |
| `INSTALLED` | yes          | yes         | no (gated off)      | Enable → `ENABLED`; Uninstall → `AVAILABLE` |
| `ENABLED`   | yes          | yes         | yes                 | Disable → `INSTALLED`; Uninstall → `AVAILABLE` |
| `BROKEN`    | yes          | yes         | no                  | Uninstall → `AVAILABLE` (manual repair first, then Install again) |
| (gone)      | no           | no          | —                   | (delete-modifier removed the zip)    |

`DISCOVERED` as a status name retires. "Discovered" was the old
conflation of "we have a row but it's not installed" with "the zip is
on disk and installable." In the new model, "the zip is on disk and
installable" has no DB row at all — it surfaces in the catalog
endpoint by reading the filesystem. The existing
`NeuralModifierStatus.DISCOVERED` enum value stays in fixtures for
backwards compat of historical install logs, but new installs don't use
it.

**Bug fix: orphan semantics.** Snapshot the set of
`(content_type_id, object_id)` pairs for every contribution **before**
the delete loop. After the loop, compare: IDs in the snapshot whose
target no longer exists in the DB were resolved by this uninstall —
directly deleted or cascade-deleted. IDs in the snapshot whose target
still exists are the real bug (contribution pointed at a row the
uninstall couldn't reach — should not happen). "True orphans" are
contributions whose target was already missing at snapshot time. The
event payload splits these: `contributions_resolved` (deleted or
cascaded), `orphaned_ids` (target was missing at snapshot), plus a new
`contributions_unresolved` (target still exists post-loop — should
always be empty; non-empty means a bug to investigate).

### Task 16 — Surface 1 implementation (backend) — **LANDED 2026-04-20**

See `TASKS.md` → "Recently Done — Modifier Garden Surface 1" for the
shipped shape. Scope below is kept for reference.

**Scope.**

- New catalog endpoint: `GET /api/v2/neural-modifiers/catalog/` returns
  one entry per zip under the catalog root. Each entry is the unzipped
  `manifest.json` plus `{ "installed": bool }` (true iff a
  `NeuralModifier` row exists for that slug). Reads manifests via
  `zipfile.ZipFile(path).read('manifest.json')` — no extraction.
- Rewrite `install_bundle_from_archive` to: unzip archive to tempdir
  under `neural_modifiers/_staging/<slug>/`, run the existing
  `install_bundle(slug)` codepath against the extraction, `shutil.rmtree`
  the tempdir on both success and failure. The runtime tree assumption
  (`neural_modifiers/<slug>/` persists) goes away — all state lives in
  the DB and the catalog zip.
- Modify `install_bundle` path resolution so it can accept the staging
  tempdir as its source (currently hardcoded to `modifier_genome/<slug>/`).
  Cleanest shape: split into `install_bundle_from_source(source_path)`
  (the current function's body, parameterized) and keep
  `install_bundle(slug)` as a wrapper that passes `modifier_genome/<slug>/`
  — for dev-flow `./manage.py build_modifier` use only. The API / UI
  path uses `install_bundle_from_archive → install_bundle_from_source`.
- New `delete` action on the viewset: removes the zip from the catalog
  dir. Refuses if a live DB row exists (must uninstall first). Returns
  400 with a clear message in that case.
- Uninstall-event orphan fix: snapshot object_ids before the delete
  loop; split event_data into `contributions_resolved`,
  `orphaned_ids`, `contributions_unresolved`. Update
  `UninstallCapturesAllOrphanedIdsTest` and add
  `UninstallCleanInstallEmitsZeroOrphansTest` (repro of the 53/260 bug:
  install → uninstall immediately → assert `orphaned_ids == []`).
- Rename the misleading `build_modifier` command to something honest
  (candidate: `install_modifier_from_source`) — or leave it and add a
  one-line docstring clarifying it's the dev-flow install-from-source
  command, distinct from the API install-from-zip path. Michael's call.
  Not blocking.
- Migrate Unreal into the new flow: script that reads
  `modifier_genome/unreal/` and produces `neural_modifier_catalog/unreal.zip`.
  Add to `are-self-install.bat` **only** as a dev-setup convenience —
  the catalog zip is not a committed artifact; it's derived from the
  genome dir.

### Task 17 — Surface 1 implementation (frontend) — **LANDED 2026-04-20**

Shipped in `are-self-ui`. See that repo's `TASKS.md` + the
`ModifierGardenPage.tsx` rewrite. Scope below is kept for reference.

**Scope.**

- `ModifierGardenPage.tsx` list source changes: instead of only
  `GET /api/v2/neural-modifiers/`, merge `/api/v2/neural-modifiers/`
  (installed rows) with `/api/v2/neural-modifiers/catalog/` (zip
  entries). Catalog entries whose slug has a matching installed row
  use the installed row's status + contribution count; catalog entries
  with no installed row render as `AVAILABLE`.
- `renderActionButton` redesign: AVAILABLE rows show an **Install**
  button (primary affordance). INSTALLED rows show an **Enable**
  button + **Uninstall** (secondary). ENABLED rows show **Disable** +
  **Uninstall**. BROKEN rows show **Uninstall** + an "inspect" link.
  Gone entirely: the disabled-Enable-with-tooltip dead-end.
- "Delete modifier" action on AVAILABLE rows (maybe behind an overflow
  menu — it removes the zip file and the row disappears from the
  catalog). Confirmation dialog: "This removes the Unreal bundle from
  your computer. You'll need to re-obtain it to reinstall."
- The install button on AVAILABLE rows calls a new endpoint
  `POST /api/v2/neural-modifiers/catalog/<slug>/install/` that runs
  the unzip→install→nuke flow on the server's existing zip. (The file-
  upload install flow from the April-19 REST-surface pass stays —
  that's for bundles the user is bringing to the machine. The catalog-
  install flow is for bundles already on the machine.)
- Kill the `STATUS_DISCOVERED` branch from `renderActionButton`.
  "Discovered" is not a surfaced state anymore.

### Acceptance criteria (both tasks together)

- Fresh checkout: `are-self-install.bat` runs, catalog dir has
  `unreal.zip`, garden shows one AVAILABLE row labeled "Unreal Engine."
- Click Install on that row → spinner → row flips to INSTALLED with
  300+ contributions. Zip still on disk; extraction tempdir gone.
- Click Enable → row flips to ENABLED. Start a reasoning session, the
  UE parietal tool appears in the picker (Task 13).
- Click Disable → row flips back to INSTALLED. Tool drops from the
  next session's picker.
- Click Uninstall → row flips back to AVAILABLE (DB row + contributions
  gone; zip still on disk). UNINSTALL event payload shows
  `orphaned_ids: []` and `contributions_unresolved: []`.
- Click Install again (re-install round-trip) → clean, no errors, same
  contribution count. (Proves the uninstall was complete.)
- Click Delete → zip removed; row disappears from the catalog entirely.
- A 10-year-old can drive every transition with no terminal open.

---

## April 19 design direction — Surface 2 (developer package / edit)

> **Status: deferred. Not in scope for Surface 1 implementation. Writing it
> down now so it doesn't get lost.**

**Context.** The Unreal bundle as committed is "severely damaged" (one
graph has 3 Begin Play nodes). Hand-fixing is not realistic ("I don't
speak UUID"). This means Surface 1 ships without an end-to-end proof
against a real bundle until Surface 2 tooling exists. That's an
acknowledged gap, not a blocker — Surface 1 can be acceptance-tested
with a minimal synthetic bundle.

**Direction (leaning option B).** In-app "save to bundle" affordance on
any endpoint's editor — environments, neural pathways, effectors,
executables, context variables, switches, tool definitions, anything
the user might want to ship. Each editor grows a secondary action:
"Save to bundle…" → modal picking a target bundle (existing or new) →
server-side the row (and any dependent rows per a to-be-defined
dependency policy) gets serialized into that bundle's
`modifier_data.json`, the manifest's hash updates, and the catalog zip
is rebuilt.

**Open questions (no answers yet — capturing, not ruling):**

1. **Dependency closure.** "Save this NeuralPathway to the bundle" —
   does that drag in every Neuron the pathway references? Every
   Executable? Every Effector? Best guess: yes, with a preview dialog
   that shows exactly which rows will be captured and lets the user
   uncheck individuals.
2. **Cross-bundle FK rules.** The `modifier_genome/README.md` rule is
   "no cross-bundle FKs." Surface 2 can enforce this at save time: if
   capturing row X would require row Y that belongs to a different
   bundle, refuse with a message pointing at the conflict.
3. **UUID preservation on round-trip.** Row edited in-place after
   bundle-save: does the bundle's next export refresh that row's entry
   in `modifier_data.json`, or does the bundle become stale? Probably
   refresh-on-save — the bundle is "live" while you're editing its
   rows. Upgrade flow (Task 15) handles downstream propagation.
4. **Per-endpoint UX.** Does every single viewset editor grow the
   action, or is it centralized somewhere (a "bundle composer" page
   that shows all candidate rows and lets you check-box them in)?
   Leaning per-endpoint for discoverability; a central composer can
   come later.
5. **Bundle-author identity / permissions.** Saving to a bundle mutates
   its source. Multi-user install would need permission gating; single-
   user (Michael's current scipraxian setup) doesn't.

**Not scope. No tickets. This section exists to be revisited after
Surface 1 is green and the unreal bundle's damage is visible in
concrete terms.** Revisit trigger: Surface 1 acceptance passes on a
minimal synthetic bundle AND Michael still can't hand-fix Unreal.

---

## April 20 design direction — addons as a fourth registration surface

> **Status: deferred until Tasks 8 / 11 / 12 / 15 are landed and
> Surface 1 dogfoods cleanly on Unreal. Not in scope for this plan.
> Durable home is the `TASKS.md` Backlog entry "Addons as a fourth
> NeuralModifier registration surface." Captured here because the
> design is structurally parallel to the NeuralModifier bundle
> contract — when this plan file gets deleted, lift this section into
> whatever supersedes it.**

**Context.** Dogfooding the Focus addon against an identity disc that
doesn't have it installed (Thalamus, in the April 20 Cowork discussion)
surfaced that the fizzle enforcement at
`parietal_lobe/parietal_lobe.py:231-256` runs on every tool call
regardless of addon membership — the check at
`identity/addons/focus_addon.py` only gates LLM prompt injection, not
enforcement. The focus/XP ledger at lines 280-287 has the mirror leak:
silent state mutation on every successful tool call. Thalamus plays
the Focus game blind — no rules prompt, full mechanics behind its back.

The addon system is a second, half-built extension surface living
alongside the NeuralModifier system with remarkable structural overlap
— enough that finishing one and then retrofitting the other to match
is the cheaper path than finishing them separately.

**Parallels with the landed NeuralModifier work.**

1. **Task 13 is the template.** Parietal tool-set gating on
   ENABLED-bundle state — "a contribution is gated at query time on
   the contributing entity's state" — is the exact shape the addon
   fizzle wants. Same pattern, gate missing.
2. **Registration surfaces are already a pattern.** The three
   bundle-time surfaces (`register_parietal_tool`,
   `register_native_handler`, `LogParserFactory.register`) share one
   idempotent unregister-then-register idiom. An addon lifecycle-hook
   contract is functionally a fourth surface using the same idiom —
   zero invention, same docs, same `handlers.py` entry-module
   convention.
3. **`IdentityAddon` is a Pass 2 vocabulary flip.** Same category as
   the Hypothalamus vocab that got flipped wholesale: a
   NeuralModifier-extensible vocabulary table with integer PKs today
   and no reason to stay that way. `IdentityAddonPhase` stays
   integer-PK — it's a protocol enum, same tier as `SpikeStatus` et
   al.
4. **Task 15 infra covers the bundle-version case for free.** Semver
   + requires + upgrade already shipped. A future "Combat Game"
   bundle declaring `requires: [{slug: 'focus_game', version_spec:
   '>=1.0'}]` Just Works.

**Direction (leaning).**

1. Promote the addon from function to class with optional hook
   methods: `on_build_payload(turn) -> list[Message]` (current
   behavior), `on_pre_tool_call(turn, tool_def, args) ->
   Optional[Veto]`, `on_post_tool_call(turn, tool_def, args, result)
   -> Optional[StateDelta]`, `on_turn_end(turn) -> None`. Narrow typed
   signatures — addons return decisions / deltas, dispatchers apply
   them. Kills the current smell where `focus_addon` reaches across
   to mutate `session` during prompt assembly (the
   `turn.apply_efficiency_bonus()` call).
2. Add `register_addon` / `unregister_addon` as the fourth
   registration surface. Bundle entry modules call it from
   `handlers.py` alongside existing `register_native_handler` calls.
   Same unregister-then-register idempotency rule, same
   `RuntimeError` on slug collisions across core + prior-bundle
   registrations.
3. Flip `IdentityAddon` to UUID-PK. Tier placement: core-shipped
   addons in `initial_phenotypes` (or `zygote` if load-bearing for
   tests — probably not, since addons are per-disc opt-in); no
   class-constant rows today, so nothing needs `genetic_immutables`.
   Bundle-contributed addons ride through `modifier_data.json` like
   any other contribution.
4. Extract Focus Game into
   `neuroplasticity/modifier_genome/focus_game/`. Bundle ships the
   `focus_addon` class, the `focus_modifier` / `xp_reward`
   `ToolUseType` rows it depends on, and owns its state.
   `parietal_lobe.py` goes back to dumb tool execution + lifecycle
   dispatch. Mirrors Unreal's role as the dogfood bundle for the
   other three registration surfaces.

**Open questions (no answers yet — capturing, not ruling).**

1. **Addon state storage.**
   `session.current_focus` / `max_focus` / `total_xp` are columns on
   `ReasoningSession` today. Cleanest end-state is an addon-scoped
   state table keyed by `(session_id, addon_slug)` with a JSON blob
   — future addons don't need core migrations. Cheaper interim is
   keeping the columns but having `focus_addon` own them exclusively.
   The hook contract shouldn't foreclose either path.
2. **Composition semantics.** Two addons both implementing
   `on_pre_tool_call`: leaning "first non-None wins" (ordered by
   phase) for veto-style hooks; additive for delta-style hooks. Pick
   once, document, enforce — if left implicit, every addon author
   picks a different default.
3. **Core-shipped addon lifecycle.** The four addons in
   `ADDON_REGISTRY` today (`normal_chat_addon`, `river_of_six_addon`,
   `prompt_addon`, `your_move_addon`) are core behavior, not
   modifier-contributed. Do they stay core-registered (bypassing the
   registration surface) or move to a notional "core bundle" that
   ships core behavior as contributions? Probably stay
   core-registered — the surface is the *extension* point, not the
   only path to register — but call the question out so the answer
   is deliberate.
4. **`function_slug` legacy.** At least one existing fixture row
   ("Focus Game" / pk=2 / `function_slug=None`) is dead weight. A
   cleanup pass belongs in this task, not the stop-gap.

**Stop-gap (not this task).** The one-line addon-presence gate on the
fizzle + ledger at `parietal_lobe.py:231-287` lands independently and
gets deleted when this task lands. Captured in `TASKS.md` Backlog under
the same title.

**Not scope. No tickets.** This section exists to be revisited after
Tasks 8 / 11 / 12 / 15 are all green and Surface 1 dogfoods cleanly on
Unreal. Revisit trigger: the "Not landed" items in this plan are all
empty AND the `TASKS.md` Backlog entry is next up by priority. At that
moment, promote this section into a real task scoped against the
then-current state of the addon and NM code.

---

## Task 8 — Unreal bundle end-to-end verification

**Status (April 19).** The code-side of the Unreal extraction has
landed: entry-module package at
`neuroplasticity/modifier_genome/unreal/code/are_self_unreal/`, native
handler and MCP tool registered from it, log parser strategies
registered from it, `modifier_data.json` populated with
ContextVariables and related rows. What has **not** been verified is
the full install → enable → exercise → disable → re-enable →
uninstall round-trip, and in particular whether every UE-specific row
has been moved out of core fixtures into `modifier_data.json`. Without
that verification, we don't know clean isolation actually holds.

**Why this is #1.** Until the round-trip passes, every later task
risks building on a broken assumption about what clean install means.
Task 8 is the foundation acceptance test for the whole feature.

**Scope.** Follow the nine-step protocol in `UNREAL_E2E_HANDOFF.md`.
Any UE-named row discovered in core fixtures during Step 1 gets moved
into `modifier_data.json` (UUID literal preserved, removed from its
core fixture) until Step 1's leakage check returns zero.

**Acceptance criteria.**

- Step 1 baseline: core-only fixture load + full test run returns
  zero UE-named rows and a known-good pass count.
- Steps 2–5: `build_modifier unreal` → `enable_modifier unreal` →
  full test suite → all green.
- Step 6: a live reasoning session observes
  `mcp_run_unreal_diagnostic_parser` in its tool manifest, the
  `update_version_metadata` handler firing, and a UE log parsing
  through the bundle's `LogParserFactory` strategy.
- Steps 7–8: disable drops the Parietal tool from the next session;
  enable brings it back.
- Step 9: `uninstall_modifier unreal` returns the DB to Step 1's
  state byte-for-byte; the full test suite result matches Step 1's
  baseline exactly.

---

## Task 11 — Hash-mismatch `BROKEN` transition proof

**Why.** `apps.py` already flips a row to `BROKEN` on manifest-hash
mismatch. There is no test that proves it actually fires end-to-end.
This is a "load-bearing assumption goes unverified" risk: if the
transition silently stops working, we'll notice only when a tampered
bundle gets silently trusted.

**Scope.**

- New test in `tests/test_modifier_lifecycle.py` (or a sibling file):
  install a bundle → overwrite its on-disk `manifest.json` with any
  modification → re-run boot (or call the verification codepath
  directly) → assert the `NeuralModifier` row's status is `BROKEN` and
  a `HASH_MISMATCH` event row was written with the old + new hashes.
- Same pattern for: manifest deleted entirely, `code/` dir deleted,
  `modifier_data.json` hash drift.

**Acceptance criteria.** Three red-flag conditions all produce
`BROKEN` with a diagnostic event row, and the bundle does **not**
contribute live handlers in the broken state.

---

## Task 12 — Orphaned-contribution uninstall path

**Why.** `NeuralModifier.iter_contributed_objects()` silently skips
contributions whose target was deleted out from under. The docstring
says "detect them by comparing the yielded count against
`self.contributions.count()`." Nobody does that comparison today.

**Scope.**

- Uninstall flow logs a `UNINSTALL` event whose `event_data` includes
  `{"contributions_total": N, "contributions_resolved": M,
  "orphaned_ids": [...]}` whenever M < N.
- Orphan contributions are still deleted (the contribution rows
  themselves, not their vanished targets), so the bundle cleans up
  after itself even in degraded states.
- Test: create a bundle, install it, manually delete one of its
  contribution targets from the DB, uninstall → assert event data
  records the orphan count and the contribution rows are gone.

**Acceptance criteria.** Uninstall never silently swallows orphans;
they're always named in the event log.

---

## Task 15 — Upgrade / version / dependency model

**Why.** Reinstall today creates a new `NeuralModifierInstallationLog`
row but the semantics of "upgrade" (preserving contributions whose UUIDs
survived across versions, deleting ones that didn't) are undefined.
There's no way for one bundle to declare it requires another. This is
the last piece before third-party bundles can be real.

**Scope.** Design, then implement:

- Manifest `version` semver + `requires: [{"slug": "...", "min": "..."}]`.
- Upgrade algorithm: diff old `modifier_data.json` UUIDs against new;
  contributions whose UUIDs persist are rebound, contributions removed
  in the new version are deleted (same path as uninstall for those
  rows), contributions added are inserted. Install log row records the
  upgrade pair.
- Dependency resolution on install: required bundles must be ENABLED
  (or co-installed), else install fails to `BROKEN` with a clear
  event.

**Acceptance criteria.**

- v1 → v2 upgrade of a test bundle preserves unchanged contributions
  and only removes/adds the deltas.
- Bundle A with `requires: [B]` refuses to install while B is absent.
- Same bundle installs cleanly once B is ENABLED.
- Comprehensive test coverage in `tests/test_modifier_versioning.py`.

---

---

## Frontend track (`are-self-ui`)

This is the separate, parallel track. The backend work above makes
bundles real; the FE work below makes them usable by a human sitting
in front of Are-Self. None of these depend on the others strictly —
they can be implemented in any order once the matching BE surface
exists — but the MVP set (FE-1 through FE-3) is what lets us stop
hand-running `./manage.py` commands and declare the feature human-
reachable.

Assumption: the UI consumes the same Django backend this repo defines,
over the existing REST / GraphQL layer (whichever `are-self-ui` is on
today). Where a new endpoint is needed, it's noted. Each item names
the BE task that must land first.

### FE-1 — Modifier Garden: list, install, uninstall (MVP)

**Depends on.** Tasks 6 (lifecycle commands, landed), 8 (Unreal dogfood,
in flight).

**Why.** Today installing/uninstalling bundles requires a dev's
terminal and `./manage.py modifier install <slug>`. For Are-Self to
ship to non-developers, a screen has to do this.

**Scope.**

- A new "Modifier Garden" view. Table of all `NeuralModifier` rows with
  `slug`, `name`, `version`, `author`, `status` (INSTALLED / ENABLED /
  DISABLED / BROKEN), install date, last event. Status rendered with
  color pills matching the backend enum.
- "Install bundle" button → file picker accepting the sealed bundle
  archive format (whatever `build_modifier` emits; confirm extension
  at FE-implementation time). POST to a new endpoint that wraps the
  `install_bundle` loader entry point; streams progress + errors back.
- "Uninstall" button per row → confirmation dialog showing the
  contribution count ("this will remove 312 rows across 14 models")
  sourced from a new `/api/modifiers/<slug>/impact/` endpoint. Click
  through runs `uninstall_bundle` server-side and refreshes the list.
- BROKEN status renders with an "inspect" affordance: click opens the
  latest `NeuralModifierInstallationLog` / events for that bundle and
  shows the exception text from the failed import or hash-check.

**Acceptance.**

- Human installs the Unreal bundle from the browser end to end, sees
  status flip to ENABLED, sees 300+ rows attributed to the bundle.
- Uninstall from the browser removes everything cleanly; status flips
  to (nothing — the NeuralModifier row is gone) or DISABLED/archived,
  whichever the backend settles on.
- Reinstall after uninstall round-trips clean.
- A bundle with a deliberately corrupted manifest surfaces BROKEN with
  the right error text in the inspector.

### FE-2 — Enable / disable toggles

**Depends on.** Task 13 (parietal tool-set gating on ENABLED).

**Why.** "Keep the data, stop using the tools" is a legitimate user
workflow — trying Unreal on/off mid-project without losing the hand-
tuned Effector rows.

**Scope.**

- Toggle control per row in the Modifier Garden: ENABLED ↔ DISABLED.
- Tooltip copy explains: "Disabling keeps this bundle's configuration
  but hides its tools from reasoning sessions. No data is removed."
- Toggle calls `enable_modifier` / `disable_modifier` equivalents via
  the existing REST / GraphQL surface.
- If a reasoning session is in flight, the toggle does not affect it —
  next session picks up the change. Surface this in the confirmation
  if we want to be explicit; not required.

**Acceptance.**

- Flip Unreal to DISABLED, start a new reasoning session, verify the
  Unreal parietal tools are absent from the tool picker. Flip back to
  ENABLED, verify they come back.

### FE-3 — Row-level bundle attribution in the admin-style views

**Depends on.** Task 8 landed (bundle with real contributions to
attribute).

**Why.** Once a bundle owns dozens of Effector / Neuron / NeuralPathway
/ Executable rows, editing one by hand without realizing it came from a
bundle is a foot-gun — the edit gets clobbered on reinstall / upgrade.
Users need to see provenance.

**Scope.**

- In every existing editor screen that renders a model with a
  `NeuralModifierContribution` pointing at it (Effectors, Neurons,
  NeuralPathways, Executables, Switches, ContextVariables,
  ProjectEnvironments, ToolDefinitions, ToolParameterAssignments, the
  full BE contribution list), show a read-only "Contributed by: `unreal
  bundle`" chip near the row title.
- Clicking the chip links to the bundle's row in FE-1.
- Editing a bundle-contributed row shows a banner warning: "Changes
  here will be reverted when this bundle is reinstalled or upgraded.
  For persistent changes, modify the bundle source and rebuild."
- This needs one new endpoint or a GraphQL field:
  `GET /api/rows/<content_type>/<uuid>/contribution/` returning the
  contributing bundle slug + id, null if core-owned.

**Acceptance.**

- Every row that shows up post-install has the chip. Every core row
  has no chip. Test fixture: install Unreal, pick a bundle-owned
  Effector and a core Effector, screenshot both — expected contrast is
  obvious.

### FE-4 — Parietal tool picker respects soft-lookup

**Depends on.** Task 8 landed.

**Why.** The Identity editor's `enabled_tools` picker today lists tool
IDs / names. After a bundle uninstalls, UUIDs in `enabled_tools` that
pointed at the bundle's tools no longer resolve — backend drops them
silently via `filter(id__in=...)`. The FE must match that behavior: do
not render orphaned tool chips, do not throw, do not "helpfully"
re-add them on save.

**Scope.**

- Tool picker's list of selected tools is derived by resolving each
  UUID against the current `ToolDefinition` table. Unresolvable UUIDs
  don't render and don't round-trip on save (save sends back only
  resolvable UUIDs, so the stored list shrinks on next save).
- Alternatively — and this is the more forgiving posture — keep
  unresolvable UUIDs in the stored list but render them as grayed-out
  "unknown tool (may return if its bundle is reinstalled)" chips. The
  user can remove them manually. This preserves the "reinstall brings
  them back" UX that soft-lookup enables.
- Pick one posture and document the choice. The soft-lookup design
  explicitly supports the gray-chip posture; default to that unless
  user testing says otherwise.

**Acceptance.**

- Install Unreal → `mcp_run_unreal_diagnostic_parser` shows up in the
  tool picker as a selectable chip. Enable it on Thalamus, save.
- Uninstall Unreal → Thalamus's tool picker either (a) renders the
  gray unresolved chip or (b) silently drops it, per the chosen
  posture. Either way, no crash, no 500.
- Reinstall Unreal → the tool reappears as a real selectable chip; if
  we chose option (b), the user re-enables it; if we chose option
  (a), the chip goes from gray to live automatically.

### FE-5 — Log viewer gracefully handles missing parser strategy

**Depends on.** Task 8 landed (UE log parser inside the bundle).

**Why.** Today the log viewer shows structured UE build/run logs
because `ue_tools/log_parser.py` is imported on every startup. Post-
bundle, if the Unreal bundle is uninstalled (or disabled and the
`LogParserFactory` unregister path is implemented in Task 8), a
request to parse a Spike's UE log can hit
`LogParserFactory.create(TYPE_RUN, ...)` and find no strategy.

**Scope.**

- When the backend returns "no parser registered for this log type,"
  render raw log text in a monospace block with a banner: "Structured
  parsing unavailable. Install the Unreal bundle to see build/run
  summaries."
- Do not white-screen. Do not show a stack trace to the user.

**Acceptance.**

- Uninstall Unreal with a Spike row that has a UE log attached.
  Navigate to its log view. See the raw log + banner. No error.

### FE-6 — Bundle detail page

**Depends on.** Task 8 + Task 12 (manifest introspection exposure if
it's not already there).

**Why.** The Modifier Garden list is a list. When a user is debugging
a BROKEN bundle or deciding whether to trust one, they want to look
inside.

**Scope.**

- Per-bundle detail view linked from the Garden row. Shows:
  - Manifest block (name, version, author, license, description, entry
    modules, `requires_are_self`, bundle `requires:` list once Task 15
    adds it).
  - Contribution breakdown: counts by model
    ("central_nervous_system.effector: 23 rows",
    "parietal_lobe.tooldefinition: 1 row", ...). Clickable; each count
    opens a list of the rows, each of which links to that row's editor
    with the FE-3 chip.
  - Installation log timeline: one entry per
    `NeuralModifierInstallationLog` row with its events
    (INSTALLED / ENABLED / DISABLED / UPGRADED / BROKEN), timestamps,
    any event payload.
  - Registered surfaces: "Native handlers contributed: `update_version_metadata`"
    / "Parietal tools contributed: `mcp_run_unreal_diagnostic_parser`"
    / "Log parser strategies: `build`, `run`". Sourced by introspecting
    the runtime registries (BE needs a small `/api/modifiers/<slug>/surfaces/`
    endpoint).

**Acceptance.**

- Unreal detail page shows 300+ rows broken out by model, 1 native
  handler, 1 parietal tool, 2 log parser strategies, and the full
  installation timeline from first install through the most recent
  event.

### FE-7 — Upgrade flow

**Depends on.** Task 15 (upgrade / version / dependency model).

**Why.** Once upgrades preserve contributions whose UUIDs persist,
users need a UI that (a) uploads a new version of an installed bundle,
(b) previews the diff before committing, (c) applies it.

**Scope.**

- Upload-new-version affordance on the bundle detail page.
- Server-side pre-upgrade diff endpoint: takes old slug + new archive,
  returns "rows preserved: N, rows removed: M, rows added: K, rows
  modified: L." Render as three lists with row names.
- "Apply upgrade" button commits via `install_bundle` upgrade path.
- `requires` dependency violations surface before the user commits:
  "This bundle requires `vim` bundle v0.2+ which is not installed."
  Block with a link to install `vim` first.

**Acceptance.**

- v1 → v2 upgrade of a test bundle surfaces a correct diff, commits
  cleanly, detail page reflects the new version number and new
  contributions.
- Upgrade that would violate a `requires` constraint refuses at the
  diff step with a clear message.

### FE-8 — Future: bundle marketplace / registry

**Depends on.** Everything above plus an actual registry. Out of
scope for the current plan; flagging only.

**Notes.** If / when scipraxian hosts a bundle registry, the Modifier
Garden grows a "Discover" tab that fetches a catalog and offers
one-click install. Until then this is a manual-upload flow via FE-1.
Do not build this speculatively.

### Cross-cutting UI concerns

- **Auth / permissions.** Installing a bundle mutates the database in
  large ways. Gate the Install / Uninstall / Enable / Disable /
  Upgrade actions behind the same admin role that gates schema
  changes today. Read-only roles see the Garden and bundle details
  but no action buttons.
- **Progress + errors.** Install can take many seconds on a large
  bundle (Unreal is 300+ rows, seal verification, sys.path shuffling,
  import of entry modules). Use the same progress / toast pattern
  Are-Self uses elsewhere — no silent spinners for > 2 seconds.
- **i18n / copy review.** "Bundle," "Modifier," "Contribution,"
  "Contribution count," "Installation event" — consistent across the
  UI. Avoid "plugin." (Vocabulary is locked, same as on the backend.)
- **Accessibility.** Status pills need text labels, not color-only.
  The gray unresolved-tool chips in FE-4 option (a) need a tooltip
  that explains why they're gray.

### Minimum shippable FE set

If we had to ship the moment Tasks 8–15 are green, the minimum set
is **FE-1, FE-2, FE-3, FE-4**. That covers install/uninstall,
enable/disable, row provenance, and tool-picker soft-lookup.
Everything else is a quality-of-life improvement and can follow.

---

## When this file gets deleted

When Tasks 8–15 are landed and green, the "Not landed" section above
is empty, and the modifier-garden install UI in `are-self-ui` exists
and works against a real bundle (at least the MVP set FE-1 through
FE-4): delete this file and update `CLAUDE.md`'s "Active thread"
banner to note the feature area is done. Archive the plan's contents
into `TASKS.md` as a historical marker before deletion if that feels
right — Michael's call.
