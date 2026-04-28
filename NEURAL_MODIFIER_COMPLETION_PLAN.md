# NeuralModifier Completion Plan

> **Scope.** What it takes to declare the NeuralModifier feature area
> feature-complete. Most of the backend and the frontend MVP have
> shipped as of 2026-04-20 (see TASKS.md for the history of individual
> landings); this file tracks the remaining forward work and the
> deferred design directions (Surface 2 save-to-bundle; addons as a
> fourth registration surface). Prior planning docs
> (`FIXTURE_SEPARATION_PROMPT.md`, `CC_PROMPT_*.md`, `STEP1_REPORT.md`,
> `STEP1_COMPLETE_REPORT.md`, `UUID_MIGRATION_PROMPT.md`,
> `NEUROPLASTICITY_CONSOLIDATION_PROMPT.md`, `UNREAL_E2E_HANDOFF.md`)
> all retired as their work landed. When this plan is done, this file
> gets nuked too.

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

TASKS.md is the authoritative log of what has landed — this file is
kept lean and forward-looking. As of 2026-04-20, everything below has
shipped: Tasks 6 (lifecycle commands), 9 (update_version_metadata into
bundle), 10 (UE log parsers into bundle), 11 (BROKEN-transition proof),
12 (orphan-contribution UNINSTALL payload), 13 (Parietal tool-set
gating on ENABLED), 14 (bundle-author docs), 15 (semver + requires +
upgrade), 16 (Surface 1 catalog backend), 17 (Surface 1 frontend), and
the 2026-04-20 layout consolidation (genomes / grafts / operating_room,
uninstall = row delete, staging-leak fix). Frontend MVP set — FE-1
(Modifier Garden list / install / uninstall), FE-2 (enable / disable
toggles), FE-3 (row-level attribution) — has also shipped. See
TASKS.md "Recently Done" entries for the shape of each.

**Landed — durable pointers (full history in TASKS.md):**

- **Models + loader.** `neuroplasticity/models.py` +
  `neuroplasticity/loader.py`. Public install API:
  `install_bundle_from_archive(path)`. AVAILABLE = zip on disk AND no
  DB row; uninstall DELETES the row with CASCADE.
- **On-disk layout.** `neuroplasticity/genomes/<slug>.zip` (committed),
  `neuroplasticity/grafts/<slug>/` (runtime, gitignored),
  `neuroplasticity/operating_room/` (transient scratch, gitignored).
- **Management commands.** `enable_modifier`, `disable_modifier`,
  `uninstall_modifier`, `upgrade_modifier`, `list_modifiers`,
  `pack_modifier`. (`build_modifier` retired.)
- **Boot hook.** `neuroplasticity/apps.py` → `boot.py` → `loader.boot_bundles()`.
  Hash drift / load failure flips BROKEN.
- **Registration surfaces (all idempotent via
  unregister-then-register):** `register_native_handler` /
  `unregister_native_handler`
  (`central_nervous_system/effectors/effector_casters/neuromuscular_junction.py`),
  `register_parietal_tool` / `unregister_parietal_tool`
  (`parietal_lobe/parietal_mcp/gateway.py`),
  `LogParserFactory.register` (`occipital_lobe/log_parser.py`).
- **Parietal tool-set gating.** `_fetch_tools` in
  `parietal_lobe/parietal_lobe.py` excludes contributions whose bundle
  is not ENABLED.
- **Modifier Garden Surface 1.** Catalog endpoint + install / uninstall
  / enable / disable / delete actions on `NeuralModifierViewSet`
  (`neuroplasticity/api.py`). Multipart upload installs persist the
  uploaded zip into the catalog.
- **Versioning + dependencies.** Semver validation, `requires:` block,
  upgrade algorithm preserving unchanged contributions by serialized
  PK. `upgrade_modifier` command.
- **Bundle-author reference.** Inside the Unreal bundle itself at
  `neuroplasticity/genomes/unreal.zip` (extract to see the README +
  layout).
- **Unreal-shaped bundle round-trip test.**
  `neuroplasticity/tests/test_install_unreal_bundle.py` — 6 scenarios
  against an *unreal-shaped* archive built on the fly in tmp during
  `setUp` (slug, ToolDefinition PK, native-handler slug, parietal-tool
  slug, and parser class names match the real bundle's contract; no
  production artifact is read).

**Not landed (this plan):**

Task 8 is the only remaining backend work item scoped by this plan.
Tasks 11, 12, and 15 all landed (see TASKS.md). Surface 1 (Tasks 16
and 17) landed. The frontend MVP set (FE-1, FE-2, FE-3) landed with
Surface 1.

Open bug tracked in TASKS.md, not re-scoped here:
`POST /api/v2/neural-modifiers/<slug>/enable/` returns 404 against an
installed bundle; `disable` on the same row works. Static analysis
shows the enable and disable actions as structurally identical —
almost certainly a one-line fix somewhere routing-adjacent. Does not
block Task 8 (management-command lifecycle path is unaffected).

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

Shipped. See `TASKS.md` → "Recently Done — Modifier Garden Surface 1".

### Task 17 — Surface 1 implementation (frontend) — **LANDED 2026-04-20**

Shipped in `are-self-ui`. See that repo's `TASKS.md` and the
`ModifierGardenPage.tsx` rewrite.

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

> **Status: deferred until Task 8 dogfoods cleanly on Unreal via the
> browser (the enable-button 404 is the current blocker). Not in scope
> for this plan. Durable home is the `TASKS.md` Backlog entry "Addons
> as a fourth NeuralModifier registration surface." Captured here
> because the design is structurally parallel to the NeuralModifier
> bundle contract — when this plan file gets deleted, lift this
> section into whatever supersedes it.**

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

**Not scope. No tickets.** Revisit trigger: Task 8 is green on Unreal
(browser path), enable-button 404 fixed, and the `TASKS.md` Backlog
entry is next up by priority. At that moment, promote this section
into a real task scoped against the then-current state of the addon
and NM code.

---

## Task 8 — Unreal bundle live-browser round-trip verification

**Status (April 20).** Automated round-trip coverage landed:
`neuroplasticity/tests/test_install_unreal_bundle.py` exercises
`install_bundle_from_archive` against an unreal-shaped archive built
on the fly in the test's tmp tree (slug + `ToolDefinition` PK +
native-handler / parietal-tool slugs + parser class names match the
real bundle's contract — but the committed `genomes/unreal.zip` is
never read). Six scenarios cover install, uninstall, reinstall
idempotency, operating_room cleanup, and soft-lookup on M2M edges.
Parietal tool gating on ENABLED (Task 13) has its own 5 integration
tests. What remains un-exercised is a real browser session driving
the state machine end-to-end — the sort of test a non-developer
would run.

**Scope.** Live round-trip from the Modifier Garden UI against the
committed `genomes/unreal.zip`:

1. Fresh install → garden lists the Unreal row as AVAILABLE.
2. Click Install → row flips to INSTALLED with 300+ contributions;
   operating_room is empty on disk.
3. Click Enable → row flips to ENABLED.
4. Start a reasoning session → `mcp_run_unreal_diagnostic_parser`
   appears in the tool manifest; the `update_version_metadata`
   handler fires; a UE log parses through the bundle's
   `LogParserFactory` strategy.
5. Click Disable → next session's tool picker drops the Unreal tool.
6. Click Enable again → tool comes back.
7. Click Uninstall → row flips back to AVAILABLE; contributions,
   installation logs, and events are gone; zip still on disk.
8. Reinstall round-trip → clean, no errors, contribution count
   matches the first install.

**Acceptance criteria.** A 10-year-old can drive every transition
with no terminal open. The full test suite passes both with Unreal
installed and with it uninstalled.

**Blocker.** Enable-button 404 open bug (see above) — step 3 above
fails via the UI until that's fixed. The management-command path
(`./manage.py enable_modifier unreal`) works, so Task 8 can be driven
end-to-end via the shell today if needed; but the user-facing
acceptance criterion is the browser path.

---

## Frontend track (`are-self-ui`)

MVP set (FE-1, FE-2, FE-3) **landed** as part of the Modifier Garden
Surface 1 work (2026-04-20). See `are-self-ui/TASKS.md` and the
`ModifierGardenPage.tsx` shipped shape for the current state. The
entries below are kept as reference for the remaining FE items
(FE-4 through FE-8).

Assumption: the UI consumes the same Django backend this repo defines,
over the existing REST / GraphQL layer (whichever `are-self-ui` is on
today). Where a new endpoint is needed, it's noted. Each item names
the BE task that must land first.

### FE-1 — Modifier Garden: list, install, uninstall (MVP) — **LANDED 2026-04-20**

Shipped in `are-self-ui/src/pages/ModifierGardenPage.tsx` as part of
Surface 1. Full list/install/uninstall/impact flow with Acetylcholine
refetch.

### FE-2 — Enable / disable toggles — **LANDED 2026-04-20**

Shipped. Note the open enable-button 404 bug (backend routing issue)
is the one outstanding item on the toggle path.

### FE-3 — Row-level bundle attribution in the admin-style views — **LANDED 2026-04-20**

Shipped alongside Surface 1.

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

MVP set was **FE-1, FE-2, FE-3, FE-4**. FE-1/2/3 shipped 2026-04-20.
FE-4 (tool-picker soft-lookup) is the last MVP piece. Everything else
(FE-5 through FE-8) is a quality-of-life improvement and can follow.

---

## When this file gets deleted

Remaining gates before this plan retires:

1. Enable-button 404 fixed (one-line routing bug; see top of file).
2. Task 8 live-browser round-trip passes on a fresh checkout, driven
   by a non-developer.
3. FE-4 (tool picker soft-lookup) lands — the last piece of the
   Modifier Garden user story that's not already shipped.

FE-5 through FE-8 are quality-of-life improvements and do not block
retirement. Surface 2 (save-to-bundle) and the addons-as-fourth-surface
direction have independent lives as deferred design items.

When the three gates are green, delete this file and update
`CLAUDE.md`'s "Active thread" banner to note the feature area is done.
Archive the Surface 2 and addons sections into `TASKS.md` before
deletion — both are referenced from there already.
