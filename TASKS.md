# Are-Self API — Tasks

Remaining work, sifted for the backend. See FEATURES.md for what's built.

## In Progress — ReasoningTurnDigest Side-car + Push-First Broadcast (April 18, 2026)

**Status:** Backend plumbing landed in this Cowork session. Frontend cutover and
a REST pull fallback are still open. Nuke-and-rebuild for demo data — no
backfill command.

**Why:** `ReasoningGraph3D.tsx` currently hits
`/api/v1/reasoning_sessions/{id}/graph_data/` which returns the entire session
as one blob — every `ReasoningTurn.model_usage_record.response_payload`,
every ToolCall, every Engram. On the target machine (GPU + RAM already pegged
by Ollama) the blob load wedges the UI. The fix is incremental digest pushes
during the live session, with the fat payload fetched only on explicit click.

**Design (locked in by Michael):**

- **NO polling.** Primary path is push via Acetylcholine. A REST pull is a
  safety-net fallback, not the main path.
- **Sidecar, not fields on `ReasoningTurn`.** A new 1:1 table
  (`ReasoningTurnDigest`) with `OneToOneField(primary_key=True)` to the
  turn. Satisfies the immutability / UUID-PK directive without adding a
  separate id column. Digest is discardable and recomputable from the turn.
- **Trigger:** `post_save` on `ReasoningTurn` when `model_usage_record` is
  populated (the turn has finished its LLM round-trip). Skips raw=True
  fixture loads.
- **Acetylcholine broadcast:** `receptor_class='ReasoningTurnDigest'` (NOT
  `ReasoningSession` — the digest is itself a domain entity, per the
  `receptor_class` convention in CLAUDE.md). Vesicle carries the ENTIRE
  digest payload so the UI doesn't have to round-trip on push.
- **Nuke-and-rebuild.** Zero active users; Michael has been wiping for demo
  videos anyway. No backfill management command.

**What landed this session (backend):**

- `frontal_lobe/models.py` — `ReasoningTurnDigest` model + its migration
  (Michael wrote these by hand). Fields: `turn` (OneToOneField PK),
  `session` (FK), `turn_number`, `status_name`, `model_name`, `tokens_in`,
  `tokens_out`, `excerpt`, `tool_calls_summary` (JSONField list),
  `engram_ids` (JSONField list).
- `frontal_lobe/digest_builder.py` — pure functions:
  `build_and_save_digest(turn)` (idempotent `update_or_create` upsert),
  `build_digest_payload(turn)` (assembles the kwargs),
  `digest_to_vesicle(digest)` (serializes to the on-wire shape). Extractors:
  `resolve_status_name`, `resolve_model_name`, `extract_excerpt` (mirrors
  the UI's `extractThoughtFromUsageRecord` — handles both direct
  `{role, content}` and OpenAI `choices[0].message` shapes),
  `build_tool_calls_summary` (compact `{tool_name, success, target}` —
  explicitly NOT args or result_payload), `build_engram_ids`. Constants:
  `EXCERPT_MAX_LEN=300`, `TOOL_TARGET_MAX_LEN=120`, `TOOL_TARGET_KEYS=
  ('target', 'path', 'name', 'id', 'file')`, `MCP_RESPOND_TOOL=
  'mcp_respond_to_user'`. No side effects outside the one
  `update_or_create` call.
- `frontal_lobe/signals.py` — `@receiver(post_save, sender=ReasoningTurn)`
  on `write_reasoning_turn_digest`. Skips raw=True and skips when
  `instance.model_usage_record_id is None`. Calls
  `build_and_save_digest()` inside try/except; failure logs
  `[FrontalLobe] Failed to build digest for turn %s` and returns without
  broadcasting. On success, `broadcast_digest(digest)` fires Acetylcholine
  with `receptor_class='ReasoningTurnDigest'`, `dendrite_id=str(turn_id)`,
  `activity='saved'`, `vesicle=digest_to_vesicle(digest)`. Broadcast
  failure is independently caught + logged; digest stays saved.
- `frontal_lobe/apps.py` — `ready()` imports `signals` for side-effect
  registration.

**Companion UI work shipped this session (see `are-self-ui/TASKS.md`):**

- `ReasoningPanels.tsx` — session-card delete (`DELETE /api/v1/reasoning_sessions/{id}/`
  — v1 and v2 routers mount the same ModelViewSet, no backend change
  needed), turn count + datetime + relative "ago" via `formatAgo()`.
- `types.ts` — `ReasoningSessionData` gained `turns_count?: number` and
  `modified?: string`. `ReasoningSessionMinimalSerializer` already exposed
  both, so no backend serializer work was needed.

**What's landed since the Cowork session (April 18):**

- [x] **~~`DigestSerializer` + `graph_data?since_turn_number=N` pull fallback.~~**
  `DigestSerializer` in `frontal_lobe/serializers.py` is keyed identical
  to `digest_to_vesicle` (a custom `_IsoformatDateTimeField` keeps
  `created`/`modified` byte-identical to the vesicle so push/pull do
  not drift). `ReasoningSessionViewSet.graph_data` now reads
  `?since_turn_number=N` (defaults to -1 — returns the full history
  when omitted, since real turns start at 1), 400s on non-integer
  input, and returns `DigestSerializer(qs, many=True).data` ordered by
  `turn_number`. The old blob shape is gone; `ReasoningSessionGraphSerializer`
  and `SessionConclusionSerializer` were removed with it.
- [x] **~~Tests for the digest signal + builder.~~**
  `frontal_lobe/tests/test_digest.py` — 16 tests across
  `DigestSignalTest` (skip paths, broadcast wiring, idempotence, raw=True,
  builder-failure log isolation) and `DigestBuilderTest` (excerpt across
  direct/OpenAI/mcp_respond shapes, truncation, malformed payloads,
  missing FK chain, tool-call summary tri-state, unfiltered engram_ids,
  serializer/vesicle dict equality, payload defaults). Full project
  suite: 527 passed, 8 skipped, 0 failed.

**What's still open:**

- [ ] **Frontend cutover.** `ReasoningGraph3D.tsx` (and the inspectors that
  currently read `response_payload` out of the blob:
  `FrontalLobeView.tsx`, `FrontalLobeDetail.tsx`, `ReasoningPanels.tsx`,
  `SessionChat.tsx`) swap the blob GET for
  `useDendrite('ReasoningTurnDigest', null)` + a client-side filter on
  `vesicle.session_id`. Full per-turn payload (request/response, full tool
  args/results) is fetched on explicit click via
  `/api/v2/reasoning_turns/{id}/` — never cached on the session object.
  Paired UI task in `are-self-ui/TASKS.md`.
- [ ] **Apply the migration + nuke-and-rebuild demo data.** Michael's
  call; not a CC task.

**Open sub-decisions (Michael to rule, not blocking initial cutover):**

- Filter `engram_ids` on `is_active=True`? Currently unfiltered — the
  frontend decides what to render. Leaning: keep unfiltered; the digest
  is a view, not an authority.
- Additional `TOOL_TARGET_KEYS` beyond `('target', 'path', 'name', 'id',
  'file')`? Kept small on purpose — purely cosmetic.

**Related items closed by this work (see below):**

- "Reasoning session deletion" is frontend-done (DELETE against the
  existing v1 route works). Pruning stays deferred — can't trim
  mid-session without respinning tool-call side effects.
- "ReasoningGraph3D — large sessions take forever to load" on the UI side
  is partially addressed: the digest side-car + push is the "pre-compute
  at turn close" arm of the April 13 plan. The
  `graph_data?since_turn_number=N` + frontend cutover pieces are still
  open above.

## Recently Done — Walker consolidation + save transit-row fix (2026-04-25, late afternoon)

Closing the round-trip gap. Save now packs faithful unreal-style
bundles; cascade and read paths share one walker.

**Walker consolidation:** the FK / M2M / reverse-FK traversal lives in
``neuroplasticity/graph_walker.walk_genome_reach`` as a single
function with two flags: ``reverse_fk`` (off by default to match the
original read-only behaviour) and ``transit_reverse_fk_sources``
(model classes from which reverse-FK is allowed to descend into the
transit allow-list). ``build_bundle_graph`` now seeds the walker with
all owned rows and forward-walks (no behaviour change to the read
mode); ``cascade_pathway_genome`` calls it with
``reverse_fk=True, transit_reverse_fk_sources=(NeuralPathway,)`` so
reach descends from a Pathway to its Neurons / Axons and forward to
the Effectors / Executables / argument-assignments without later
reverse-walking from Effector back to other Neurons in neighbouring
user content. ``genome_cascade.py`` is now ~150 lines smaller, just
the conflict policy + transactional stamp pass plus a
``reachable_genome_rows`` shim for backward-compat with the test.

**Cascade policy is additive.** The earlier policy refused on
canonical or cross-bundle ownership in reach, which broke immediately
because ``Effector.executable`` defaults to a fixture-canonical UUID
— every cascade reaches canonical infrastructure. New policy: claim
``genome=NULL`` rows for the target, skip canonical / cross-bundle
silently, refuse only when the starting pathway itself is canonical-
owned. Clear reverts only rows owned by the pathway's current bundle.
``GenomeCascadeConflict`` now fires only on the pathway-canonical
case. Result payload gained a ``skipped`` count alongside ``stamped``
and ``unchanged``. Tests rewritten as ``CascadePolicyTest`` —
``test_other_bundle_in_reach_skipped_silently``,
``test_canonical_in_reach_skipped_silently``,
``test_canonical_pathway_refuses``.

**Save fix:** ``save_bundle_to_archive`` now also serializes the
transit children of every owned ``NeuralPathway`` —
``Neuron.objects.filter(pathway_id__in=owned_pathway_ids)``,
``Axon.objects.filter(pathway_id__in=owned_pathway_ids)``,
``NeuronContext.objects.filter(neuron__pathway_id__in=...)``. Three
explicit queries, no walker (cleaner than walker-collect for save
because we don't want SpikeTrain / Spike pulled in even
accidentally). The ``_load_modifier_data`` install side already
deserialised non-GenomeOwnedMixin rows correctly; this closes the
round-trip. Saved zips no longer land empty pathway containers.

**Confirmed not pulled into reach:** ``SpikeTrain`` and ``Spike`` —
they inherit ``UUIDIdMixin`` + ``CreatedAndModifiedWithDelta`` +
``ProjectEnvironmentMixin``, *not* ``GenomeOwnedMixin``, and are not
in the transit allow-list. Telemetry stays out of bundle content.

## Recently Done — Neuroplasticity CRU surface (2026-04-25, afternoon)

Closing the "I have install/uninstall and that's it after six days"
gap. Bundle-level CRUD now has Create, Read, the keystone Update
(genome cascade + Save-with-version-bump), and the existing Delete.
Enable/Disable removed as never-asked-for scope.

**Backend surface changes:**

- **`neuroplasticity/api.py`** — removed `enable` / `disable`
  @actions. Added `POST /api/v2/neural-modifiers/create/` taking
  `{slug, name, version, author, license}` for empty-bundle
  scaffolding; returns 201 with the standard
  `NeuralModifierDetailSerializer` payload. 409 on slug collision
  (DB row OR catalog zip), 400 on invalid manifest fields. Fires
  Acetylcholine `'create'`. No restart trigger — empty bundle has no
  imports to flush.
- **`neuroplasticity/loader.py`** — `enable_bundle` / `disable_bundle`
  removed. Added `create_empty_bundle(slug, *, name, version, author,
  license)` that scaffolds `grafts/<slug>/` with empty
  `manifest.json` + `modifier_data.json` + `code/` and creates the
  INSTALLED row + initial event log. `save_bundle_to_archive` now
  always semver-patch-bumps the version: parses current version,
  increments patch, mirrors the new value onto
  `NeuralModifier.version` and `manifest_json`, writes the bumped
  manifest into the zip. Returns gained `previous_version` and
  `new_version` keys. `iter_installed_bundles` simplified to
  INSTALLED-only after the ENABLED status retirement.
- **`neuroplasticity/genome_cascade.py`** — new module. BFS reach from
  a starting GenomeOwnedMixin row (forward FK / M2M + reverse FK
  whose other end is also GenomeOwnedMixin), then stamps or clears
  the `genome` FK on each row in a `transaction.atomic` block.
  Conflict policy: refuse if reach hits a canonical-owned row or a
  row owned by a non-target NeuralModifier — `GenomeCascadeConflict`
  carries the conflict descriptors. Reach contract: graph_walker
  symmetry — the cascade stamps exactly the rows
  `build_bundle_graph` later reports as `owned`.
- **`central_nervous_system/api_v2.py`** — added
  `POST /api/v2/neuralpathways/<id>/set-genome/` on
  `NeuralPathwayViewSetV2`. Body
  `{"genome_slug": "<slug>" | null}`. 400 on missing field, 404 on
  unknown slug or pathway, 400 if the slug is canonical, 409 with
  the conflict tree on `GenomeCascadeConflict`. Returns the cascade
  result `{pathway_id, target_slug, stamped, unchanged, rows}`.
- **`central_nervous_system/serializers_v2.py`** —
  `NeuralPathwaySerializer` now exposes read-only `genome_slug` so
  the BEGIN_PLAY inspector dropdown can pre-populate.
- **`neuroplasticity/models.py`** — `NeuralModifierStatus` state
  machine docstring rewritten: `AVAILABLE -> INSTALLED <-> BROKEN`
  is the live shape; `ENABLED` (3) and `DISABLED` (4) marked retired
  but kept in the enum for historical log-event compat (same pattern
  as `DISCOVERED`).
- **`neuroplasticity/management/commands/enable_modifier.py`** and
  **`disable_modifier.py`** — overwritten as deprecation stubs that
  raise `CommandError`. The Linux sandbox couldn't unlink them off
  the Windows mount during the rip; delete from a normal terminal:
  `del neuroplasticity\management\commands\enable_modifier.py` and
  `del neuroplasticity\management\commands\disable_modifier.py`.

**Frontend surface changes:**

- **`are-self-ui/src/pages/ModifierGardenPage.tsx`** — Enable /
  Disable button + chip filters removed; `STATUS_ENABLED` /
  `STATUS_DISABLED` constants retired (status pill colors stay so
  historical events render correctly). Added Save button on
  installed rows (`POST /save/`, optimistic local version bump). Added
  New Bundle button + modal (slug / name / version / author /
  license, posts to `/create/`).
- **`are-self-ui/src/components/CNSInspector.tsx`** — accepts
  `pathwayId` prop. New GENOME accordion, only visible when the
  selected node's `effector === EFFECTOR.BEGIN_PLAY`. Dropdown lists
  installed bundles + a "None" option; on change posts to
  `/api/v2/neuralpathways/<id>/set-genome/`. Surfaces 409 conflict
  detail + per-row conflict list inline.
- **`CLAUDE.md`** — state-machine bullet rewritten; retired-status
  note rolled in.

**Tests:**

- New `neuroplasticity/tests/test_genome_cascade.py`:
  `CascadeReachTest` (reach walks through transit-model nodes —
  Neuron + Axon — to reach the bundle-owned Effector on the far
  side), `CascadeStampTest` (stamp writes only on the
  GenomeOwnedMixin rows in reach: pathway + Effector, never on
  transit; clear and idempotence verified), and
  `CascadeConflictTest` (canonical and other-bundle ownership on
  the Effector both refuse with `GenomeCascadeConflict`; rollback
  verified).
- `neuroplasticity/tests/test_modifier_lifecycle.py` —
  `EnableDisableRoundTripTest` and `ListModifiersReportsStatusTest`
  both removed; module docstring updated.
- `neuroplasticity/tests/test_api.py` — `test_enable_disable_actions`
  removed.
- `neuroplasticity/tests/test_canonical_hidden_from_viewset.py` —
  `test_enable_action_404s_for_canonical` and
  `test_disable_action_404s_for_canonical` removed.

**Architectural ruling.** Neuron / Axon / NeuronContext are NOT
`GenomeOwnedMixin` and won't become so. Their bundle membership is
transitive via the pathway FK chain. Cascade walker steps through
them as transit; save serializes them via explicit pathway-rooted
queries. Confirmed by Michael 2026-04-25.

**Outstanding follow-ups (not blocking):**

- `POST /api/v2/neural-modifiers/<slug>/upgrade/` HTTP wrapper for
  `loader.upgrade_bundle` — already exists as a CLI; thin HTTP
  wrapper would make Path B (fix-zip-externally → upgrade-in-place)
  reachable from the UI without a terminal trip.
- `cascade_pathway_genome` runs synchronously inside the request.
  For very wide pathways this could grow uncomfortable; if it does,
  promote to a Celery task with the response carrying a tracking
  id. Not needed for current pathway sizes.

## Recently Done — Restart-coordinated install/uninstall + UI optimistic updates (2026-04-25, morning)

Closing 4-5 days of stuck-on-install/uninstall work. The original
symptom: rapid install → uninstall → install on the Modifier Garden
returned 409, leaking `[Synaptic Cleft] Dendrite disconnected from
spike` and `Failed to install unreal` in the console.

Root cause was layered: `shutil.rmtree(runtime, ignore_errors=True)`
silently failed on Windows because the live Daphne process held
imported bundle modules in `sys.modules` (file handles still locked).
DB row got deleted, directory persisted, next install hit the
`grafts_root() / slug` existence guard at `loader.py:212` and 409'd.

**Architectural ruling.** Disk and in-memory state are ephemeral;
restart is the atomic operation. Uninstall stops touching disk
synchronously; boot rebuilds from authoritative DB + zip state in a
fresh process. No unregister wiring, no genome-aware registries, no
new state-machine columns — the restart sweeps everything.

**Surface changes:**

- **`neuroplasticity/loader.py`** — `uninstall_bundle` no longer
  rmtrees the runtime dir; only `_remove_code_from_path` + DB delete.
  `boot_bundles` got an orphan sweep pass before the import loop:
  any `grafts/<slug>/` with no matching `NeuralModifier` row is
  rmtree'd cleanly (loud, no `ignore_errors`) because the sweep runs
  in a freshly-spawned process with empty `sys.modules`.
- **`peripheral_nervous_system/autonomic_nervous_system.py`** —
  `SystemControlViewSet.restart`'s body extracted into module-level
  `trigger_system_restart()` callable. New helper
  `_delayed_daphne_reload()` `time.sleep(1.0)`s then
  `Path('config/__init__.py').touch()` to trigger Django's
  autoreloader (exit code 3 → parent respawns child). Stale
  `--pool=solo` celery cmd swapped for `--concurrency=4 -P threads -E`
  to mirror `are-self.bat:33` topology.
- **`neuroplasticity/api.py`** — `install`, `catalog_install`, and
  `uninstall` actions now call `trigger_system_restart()` after
  their `_broadcast(...)` and before returning the response.
- **`are-self-ui/src/pages/ModifierGardenPage.tsx`** —
  `installFromCatalog` rewritten to apply the install response's
  authoritative `NeuralModifierDetail` directly into local state via
  filter-then-append (same pattern as `confirmUninstall`). Without
  this, the post-install Daphne autoreload eats the
  Acetylcholine-triggered refetch and the row stays stuck on
  AVAILABLE until manual refresh.
- **`are-self-ui/src/components/ModifierInstallButton.tsx`** —
  optional `onInstalled?: (data: NeuralModifierDetail) => void` prop;
  the upload-zip path calls it on success. `ModifierGardenPage` wires
  it to the same filter-then-append merge.

**Tests:**

- The two failing reinstall-cycle tests in
  `integration_tests/test_install_unreal_bundle.py` (since moved
  under `neuroplasticity/tests/`) got `loader.boot_bundles()` calls
  inserted between uninstall and reinstall. They were modeling the
  old in-process semantics; they now model the production flow
  (boot sweeps disk between cycles).
- `neuroplasticity/tests/test_api.py` — `@patch('neuroplasticity.
  api.trigger_system_restart')` decorator added to
  `ModifierApiSmokeTest.test_uninstall_action` and
  `CatalogInstallCreatesRowTest.test_catalog_install_creates_row_
  and_clears_operating_room`. Those were the only two tests hitting
  endpoints that fire the trigger; everything else either uses the
  loader directly or hits an early-return path. No global conftest
  fixture — the spawn surface is exactly two tests.

**Standing rulings landed.** Two new bullets in `CLAUDE.md` under
the project-wide rulings: (a) uninstall defers disk cleanup to
boot's orphan sweep; (b) install/uninstall API actions trigger
`trigger_system_restart`, tests must mock it. See `CLAUDE.md`.

**Architectural follow-up (not blocking, deferred).**
`trigger_system_restart` is currently called inline from
`neuroplasticity/api.py`, which mixes view logic with operational
process management. The Are-Self-native answer is to make
`autonomic_nervous_system` a *subscriber* to the Acetylcholine that
`api._broadcast` already fires for install/uninstall — the API
stops knowing anything about restart, and tests stop needing a
mock because the consumer isn't running in test mode. Mentioned
here as a future-Michael decision; today's mock is sufficient and
ships clean.

## Recently Done — NeuralModifier layout consolidation + install/uninstall bug fixes (2026-04-20)

Dogfood round-trip against the Unreal bundle flagged two live bugs and
one architectural drift:

- **Staging leak.** `catalog/unreal/install` left
  `neural_modifiers/_staging/` behind on disk.
- **Stuck row.** After uninstall, the Modifier Garden still rendered
  the Uninstall button; DISCOVERED was acting as a no-op afterlife
  that the FE couldn't cleanly reason about.
- **Three sibling root dirs** (`neuroplasticity/modifier_genome/`,
  `neural_modifier_catalog/`, `neural_modifiers/`) sprawled across
  the repo root when everything belongs under the `neuroplasticity/`
  app.

**Nomenclature lock-in.** Three directories, biological names:
`neuroplasticity/genomes/<slug>.zip` (committed archives),
`neuroplasticity/grafts/<slug>/` (runtime install trees, gitignored),
`neuroplasticity/operating_room/` (transient scratch, gitignored,
empty between ops). The unzipped `modifier_genome/` source tree is
gone — the **zip is the source of truth.** Settings constants
renamed: `MODIFIER_GENOME_ROOT` retired, `NEURAL_MODIFIERS_ROOT` →
`NEURAL_MODIFIER_GRAFTS_ROOT`, `NEURAL_MODIFIER_CATALOG_ROOT` →
`NEURAL_MODIFIER_GENOMES_ROOT`, new
`NEURAL_MODIFIER_OPERATING_ROOM_ROOT`.

**Ruling change.** AVAILABLE = zip on disk **AND no DB row**.
Uninstall DELETES the `NeuralModifier` row; contributions, logs, and
events CASCADE away. A failed fresh install also deletes its row —
no BROKEN / DISCOVERED stubs survive a failed install.  BROKEN is
now reserved for boot-time drift against a previously-working
install.

**Surface changes:**

- `loader.py`: `modifier_genome_root()` deleted; `catalog_root()` →
  `genomes_root()`; `neural_modifiers_root()` → `grafts_root()`; new
  `operating_room_root()`. `install_bundle(slug)` retired —
  `install_bundle_from_archive(path)` is the single public install
  API. `install_bundle_from_source(source, slug)` stays as the
  loader primitive used by tests and by
  `install_bundle_from_archive`. Staging leak fixed by extracting
  zips into `tempfile.mkdtemp(dir=operating_room_root())` with a
  `try/finally` that nukes the tempdir on every exit. Runtime-dir
  collision check moved BEFORE any DB writes, so a failed pre-flight
  no longer leaks a DB row.
- `api.py`: uninstall returns `{slug, uninstalled: true}` and
  broadcasts `_broadcast(None, 'uninstall', slug=slug)` because the
  modifier is gone by the time the handler returns.
- `management/commands/`: `build_modifier` and `pack_modifier`
  retired — they had no meaning once the zip became the single
  source of truth.
- `occipital_lobe/tests/test_merge_logs_nway.py`: no longer imports
  from a source tree; uses
  `neuroplasticity.test_helpers.ensure_unreal_bundle_code_on_path()`
  to extract the committed zip once per process and put its code on
  `sys.path`.
- The Unreal bundle's own round-trip test rehomed to
  `neuroplasticity/tests/test_install_unreal_bundle.py`, exercising
  `install_bundle_from_archive` against the committed
  `genomes/unreal.zip`. (The other bundle-internal tests that used
  to live inside `modifier_genome/unreal/code/are_self_unreal/tests/`
  went away with the source tree; if a future bundle needs
  internal tests they ship inside the zip.)
- `.gitignore`: `/neural_modifiers/` and `/neural_modifier_catalog/`
  replaced with `/neuroplasticity/grafts/` and
  `/neuroplasticity/operating_room/`. `genomes/` is committed.

Scoped test runs after the patch: `neuroplasticity/` + tool-gating +
tool-registration + native-handler-registration → 60 passed.

## Recently Done — Modifier Garden Surface 1: zip-on-disk catalog (2026-04-20)

Dogfooding the garden against the Unreal bundle surfaced three
failures: (1) no discovery path — installing required a dev shell;
(2) post-uninstall rows went DISCOVERED with no per-row Install
button (dead-end UX); (3) Task 12 `orphaned_ids` conflated
cascade-deleted with out-of-band deleted (53/260 false orphans on a
clean uninstall). Redesign landed in one BE pass + one FE pass.
Design rulings in `NEURAL_MODIFIER_COMPLETION_PLAN.md` under "April
19 design rulings." Surface 2 (in-app "save to bundle" on endpoint
editors) captured there as deferred.

**State machine (live):** AVAILABLE (zip on disk, no DB row) →
INSTALLED (DB row, tools gated off) → ENABLED (tools live);
uninstall drops back to AVAILABLE (zip stays); delete removes the
zip. BROKEN surfaces on hash drift / load failure. `DISCOVERED`
retired as a surfaced status — the enum value stays for backwards
compat of historical log events only.

**Backend (Task 16):**

- **New setting `NEURAL_MODIFIER_CATALOG_ROOT`** at
  `<repo>/neural_modifier_catalog/` (gitignored). `loader.catalog_root()`
  mirrors the existing `modifier_genome_root()` / `neural_modifiers_root()`
  helpers.
- **`loader.read_archive_manifest(path)`** reads `manifest.json`
  out of a bundle zip via `zipfile.ZipFile` without extraction. The
  zip's single top-level directory IS the slug; the manifest inside
  is the authority.
- **`loader.read_catalog_manifests()`** walks `*.zip` under the
  catalog root; malformed zips are logged and skipped, not fatal.
- **`install_bundle` split** into `install_bundle(slug)` (thin
  wrapper around the committed `modifier_genome/<slug>/` for the
  `./manage.py build_modifier` dev flow) and
  `install_bundle_from_source(source, slug)` — the old body, now
  parameterized so the catalog flow can hand it a staging tempdir.
- **`install_bundle_from_archive(path)` rewrite** — extracts the
  zip to `neural_modifiers/_staging/<slug>/`, runs
  `install_bundle_from_source` against it, nukes the staging dir in
  a `try/finally` (success or failure). The runtime tree at
  `neural_modifiers/<slug>/` still persists (carries the live code
  on `sys.path`); the staging dir is transient.
- **New viewset actions** (`neuroplasticity/api.py`):
  - `GET /api/v2/neural-modifiers/catalog/` — one row per zip,
    `installed` flag joined from a single `NeuralModifier.objects.filter(slug__in=…)`
    query.
  - `POST /api/v2/neural-modifiers/catalog/<slug>/install/` — 404
    if zip absent, 409 if bundle already installed, otherwise runs
    the archive-install flow.
  - `POST /api/v2/neural-modifiers/catalog/<slug>/delete/` — 400
    if DB row still exists (uninstall first), 404 if zip absent,
    otherwise `archive_path.unlink()`. Fires
    `receptor_class='NeuralModifier'` Acetylcholine with
    `activity='catalog_changed'`.
- **Multipart-upload `install` action rewrite** — an uploaded zip
  now persists as `catalog/<slug>.zip` first and runs the catalog
  flow against it, so "bring your own bundle" becomes a permanent
  catalog entry (failed uninstall leaves the zip as AVAILABLE; user
  retries Install or hits Delete — Michael's ruling, not a bug).
- **Orphan-semantics fix.** `uninstall_bundle` snapshots
  `(content_type_id, object_id)` for every contribution BEFORE the
  delete loop; outcomes partition into `contributions_resolved`
  (deleted directly or by cascade), `orphaned_ids` (target was
  already missing pre-loop — true orphan), and
  `contributions_unresolved` (target survived the loop — should
  always be empty; non-empty = real bug). Event payload keys
  updated. 53/260 false-orphan bug fixed.
- **New `./manage.py pack_modifier <slug>`** — zips
  `modifier_genome/<slug>/` into
  `neural_modifier_catalog/<slug>.zip`. Skips `__pycache__/` and
  `*.pyc`. Dev-flow only; catalog zip is derived state.
- **`are-self-install.bat` wiring** — runs
  `pack_modifier unreal --force` after fixture load. Fresh clone
  surfaces one AVAILABLE row labeled "Unreal Engine."
- **Tests.** `UninstallCleanInstallEmitsZeroOrphansTest`
  (`test_modifier_lifecycle.py:341`) is the direct repro of the
  53/260 bug — installs a 3-row CASCADE-FK bundle, forces cascade
  mid-loop via timestamp manipulation, asserts `orphaned_ids == []`
  and `contributions_unresolved == []`. Plus 6 catalog-endpoint
  smoke tests in `test_api.py` (catalog-list empty, installed-flag,
  install creates row, install-conflicts-when-installed,
  delete-removes-zip, delete-refuses-when-installed). Scoped:
  `pytest neuroplasticity/` → 63 passed, 1 skipped.

**Frontend (Task 17, in `are-self-ui`):**

- `UnifiedRow` discriminated union merges the installed
  `/api/v2/neural-modifiers/` list with the catalog endpoint;
  installed-slug wins dedup. Parallel fetch, both keyed to the
  same `NeuralModifier` dendrite event, independent `.ok` gates so
  a catalog 404 during the BE build-out degrades to empty catalog
  gracefully.
- `renderActionButton` rewrite: AVAILABLE → Install; INSTALLED →
  Enable; ENABLED → Disable; BROKEN / DISCOVERED → `null` (no
  primary action, Uninstall still renders). The disabled-Enable-
  with-tooltip dead-end is gone.
- Available rows get an overflow menu (⋯) with Delete; click-outside
  + confirm-dialog for destructive removal.
- New AVAILABLE status pill (synthetic `statusId: 0` — no collision
  with `NeuralModifierStatus` fixture ids which start at 1).
- Filter bar's `discovered` chip replaced by `available`. Any
  DISCOVERED row encountered (historical only) folds into the
  `broken` filter as a defensive fallback.

**Known open item.** `pack_modifier` currently uses an exclude
filter (`skip __pycache__/*.pyc`). Cleaner shape is include-only
(`*.py` and `*.json`), which is robust against editor swap files,
`.DS_Store`, stray `.git` remnants, and anything else a future
bundle might accidentally pick up. Tightening this is a one-line
swap; not blocking.

CC prompt files (`CC_PROMPT_MODIFIER_SURFACE_1_BE.md`,
`CC_PROMPT_MODIFIER_SURFACE_1_FE.md`) served their purpose; fine
to nuke at Michael's call.

## Recently Done — Modifier Garden REST surface (2026-04-19)

Thin DRF layer landed to let the `are-self-ui` Modifier Garden page drive
the loader over the wire.

- **`neuroplasticity/serializers.py`** — `NeuralModifierSerializer`
  (summary: status, contribution count, latest event) and
  `NeuralModifierDetailSerializer` (+installation logs with events).
  Both are read-only; mutations happen through action endpoints.
- **`neuroplasticity/api.py`** — `NeuralModifierViewSet` as a
  `ReadOnlyModelViewSet` with custom actions: `install` (multipart zip
  upload OR json `{slug}`), `uninstall`, `enable`, `disable`, `impact`
  (contribution-count breakdown by ContentType for the UI's uninstall
  confirmation). After each lifecycle op the viewset fires an
  Acetylcholine with `receptor_class='NeuralModifier'` so the garden
  view refetches via dendrite.
- **`neuroplasticity/api_urls.py`** + `config/urls.py` — registers
  `neural-modifiers` at `/api/v2/`.
- **`neuroplasticity/loader.py`** — two additions adjacent to the
  existing lifecycle functions: `install_bundle_from_archive(upload)`
  accepts a zipped bundle whose top-level directory matches the
  manifest slug and extracts into `modifier_genome/<slug>/` before
  running the usual `install_bundle(slug)`; `bundle_impact(slug)`
  returns `{slug, contribution_count, breakdown: [{content_type, count}]}`
  for the uninstall preview dialog.
- **Tests** — `neuroplasticity/tests/test_api.py` (6 smoke tests:
  list, retrieve, impact, enable/disable, uninstall, and the install
  endpoint's 400 on empty payload). Full scoped suite: 26 tests, green.

Frontend landed in `are-self-ui` — see that repo's `TASKS.md`.

## Recently Done — Task 15: NeuralModifier semver + requires + upgrade (2026-04-19)

Three sub-features landed in one pass:

1. **Semver validation** — `_validate_manifest` now parses `version` with
   `packaging.version.Version` and rejects malformed strings up-front.
   `packaging>=23.0` declared in `requirements.txt` (was already installed
   transitively at 26.0; declaration makes the dependency explicit).
2. **`requires:` block** — manifests may declare an optional `requires`
   list of `{slug, version_spec}` entries. `_validate_requires` checks
   shape, `_check_requires` resolves them at install time against
   already-installed (INSTALLED / ENABLED / DISABLED) modifiers using
   `packaging.specifiers.SpecifierSet`. Missing or version-mismatched
   dependencies raise `ValueError` before any disk copy.
3. **Upgrade command** — `./manage.py upgrade_modifier <slug>` (new file
   at `neuroplasticity/management/commands/upgrade_modifier.py`) drives
   `loader.upgrade_bundle`. The upgrade diffs new `modifier_data.json`
   against existing contributions by serialized PK, deletes dropped
   rows, creates new rows, and updates shared rows in place — preserving
   the `NeuralModifierContribution` row PKs so external FKs survive
   across versions. New `UPGRADE = 7` enum value on
   `NeuralModifierInstallationEventType` plus its row in
   `neuroplasticity/fixtures/genetic_immutables.json`. Refuses to run
   when on-disk version is not strictly newer; `--allow-same-version`
   forces a re-diff for repairs.

**Known limitation (intentional, deferred):** uninstall does NOT check
for reverse dependencies. A bundle that depends on a just-uninstalled
one will surface as a boot-time failure (its entry modules may fail to
import, flipping BROKEN). Reverse-dep protection can be a follow-up if
the noisy-failure mode bites in practice.

7 new tests in `neuroplasticity/tests/test_modifier_lifecycle.py`:
`InstallRejectsInvalidSemverTest`, `InstallRequiresSatisfiedTest`,
`InstallRequiresMissingTest`, `InstallRequiresVersionMismatchTest`,
`UpgradePreservesUnchangedContributionsTest`,
`UpgradeRefusesStaleVersionTest` (two methods).

Scoped run: `manage.py test neuroplasticity.tests.test_modifier_lifecycle`
→ 20/20 pass.

## Recently Done — Task 12: orphan-contribution UNINSTALL event payload (2026-04-19)

`uninstall_bundle` now names the orphans, not just counts them. When a
contribution's target row was deleted out-of-band before uninstall, the
`UNINSTALL` event payload captures each orphaned `object_id` (UUID
serialized as string) instead of just a count. Renamed the payload keys
per the plan: `targets` → `contributions_total`, `deleted` →
`contributions_resolved`, `orphans` → `orphaned_ids` (now a list).

Loader change: `neuroplasticity/loader.py:154-202` — captures
`orphaned_ids` inline as it walks contributions. No model / migration /
fixture changes — `event_data` is a `JSONField`. No external consumers
(grepped repo-wide for the old keys; only the loader and tests reference
them).

Tests in `neuroplasticity/tests/test_modifier_lifecycle.py`:
- `UninstallFullRollbackTest` — updated to assert the new keys (empty
  `orphaned_ids` list).
- `UninstallHandlesOrphanedContributionTest` — updated; now asserts the
  exact orphan UUID, not just the count.
- `UninstallCapturesAllOrphanedIdsTest` — new; verifies multiple
  out-of-band deletions all surface in `orphaned_ids`.

Scoped run: `manage.py test neuroplasticity.tests.test_modifier_lifecycle`
→ 13/13 pass.

## Recently Done — Task 11: NeuralModifier BROKEN-transition proof (2026-04-19)

Locked down the BROKEN flip with end-to-end coverage so the load-bearing
"tampered bundle gets refused" guarantee can't silently regress. Mode A
(hash drift) was already covered by `InstallRejectsHashDriftTest`. Added
three new test classes in `neuroplasticity/tests/test_modifier_lifecycle.py`
for the remaining BROKEN modes:

- `BootFlipsBrokenOnMissingManifestTest` — Mode B: manifest deleted post-install,
  boot flips BROKEN with one `HASH_MISMATCH` event, entry module not re-imported.
- `BootFlipsBrokenOnMissingCodeTest` — Mode C: `code/` dir deleted post-install,
  boot flips BROKEN with one `LOAD_FAILED` event carrying the `ModuleNotFoundError`
  traceback.
- `InstallFlipsBrokenOnDeserializationFailureTest` — Mode D: malformed
  `modifier_data.json` triggers the install-time atomic rollback, flips BROKEN,
  no contribution rows linger, runtime dir cleaned up, one `LOAD_FAILED`
  event with traceback.

**No loader changes needed** — `loader._boot_one` and `loader.install_bundle`
already drive `_flip_broken_with_event` on every BROKEN-worthy path. Tests
verify the contract; no production code moved.

Targeted run: `manage.py test neuroplasticity.tests.test_modifier_lifecycle`
→ 12/12 pass. Full neuroplasticity app: 12/12 pass.

## Recently Done — SessionConclusion push + pull back on the reasoning graph (2026-04-19)

The third and last domain node (after digests and engrams) restored to the
same push-first + pull-fallback contract. Goals are legacy and stay dropped.

- **`SessionConclusionSerializer`** (`frontal_lobe/serializers.py`) — read-only
  shape covering `id`, `session_id`, `status_name`, `summary`, `reasoning_trace`,
  `outcome_status`, `recommended_action`, `next_goal_suggestion`,
  `system_persona_and_prompt_feedback`, `created`, `modified`. Uses the same
  `_IsoformatDateTimeField` as `DigestSerializer` so push vesicle and pull
  response stay byte-identical.
- **`GET /api/v2/reasoning_sessions/{id}/conclusion/`** — new detail action on
  `ReasoningSessionViewSet` returning the serialized conclusion or 404. No
  separate `SessionConclusionViewSet`; a single OneToOne doesn't warrant it.
- **`post_save` broadcast** (`frontal_lobe/signals.py`) — `@receiver` on
  `SessionConclusion` fires Acetylcholine with
  `receptor_class='SessionConclusion'`, `dendrite_id=str(session_id)`,
  `activity='saved'`, and `vesicle=conclusion_to_vesicle(conclusion)`. Guards
  on `raw=True` only — SessionConclusion only exists when real (no
  `model_usage_record`-style emptiness gate applies). Failures logged under
  `[FrontalLobe]`.
- **Tests** (`frontal_lobe/tests/test_conclusion.py`) — 5 tests:
  endpoint-200, endpoint-404, post_save-fires-Acetylcholine, raw=True skip,
  serializer↔vesicle symmetry. Full pytest suite: 548 passed, 8 skipped,
  0 failed.

## Recently Done — Sessions filter on engrams + stable id on tool_calls_summary (2026-04-18)

Two targeted backend fixes that unblock the UI side of the digest cutover:

- **`EngramViewSet` now accepts `?sessions=<uuid>`** alongside the existing
  `?identity_discs=` filter (`hippocampus/api.py`). Same `.distinct()`
  pattern. The frontend uses this to pull the engrams for a single session
  in one shot when the reasoning graph mounts, so engram nodes render on
  the 3D graph again (approach-(b) override of the original digest-cutover
  approach-(a) decision — engrams are core domain data, not
  inspector-only).
- **`tool_calls_summary` entries now carry `id: str(call.id)`**
  (`frontal_lobe/digest_builder.py` → `build_tool_calls_summary`). Without
  a stable id the frontend had to match tool sub-nodes to their
  `ToolCall` rows by array index, which is fragile across retries /
  deletions / reorderings. The id lets the tool inspector look up the
  exact row on the fetched turn by pk. Model help_text and migration
  help_text updated in-place to reflect the new shape (pure metadata,
  no SQL change).
- New test `hippocampus/tests/test_engram_api.py::TestEngramFilterBySession::test_filter_engrams_by_session`
  covers the filter. `frontal_lobe/tests/test_digest.py::DigestBuilderTest::test_build_tool_calls_summary_empty_and_populated`
  and `DigestRefreshTest::test_digest_refreshes_after_tool_call_added`
  updated to assert the new id key matches `ToolCall.pk` as a string.
  Full pytest suite: 532 passed, 8 skipped, 0 failed.

## Recently Done — Digest refresh on tool_calls and engram writes (2026-04-18)

The digest side-car landed earlier in the day wired to a single `post_save`
on `ReasoningTurn` — the one where `model_usage_record` is first attached.
In that moment `turn.tool_calls` and `turn.engrams` are both empty: ToolCall
rows are created by `ParietalLobe.process_tool_calls()` *after* the save,
and Engram M2M links are written from the hippocampus on its own timeline
without re-saving the turn. Net effect: `tool_calls_summary` and
`engram_ids` were empty for every completed turn in the UI. Fix A in
`frontal_lobe/frontal_lobe.py` — after `process_tool_calls` returns, call
`build_and_save_digest(turn) + broadcast_digest(digest)` directly
(idempotent upsert, no extra UPDATE on the turn). Fix B in
`frontal_lobe/signals.py` — new `m2m_changed` receiver on
`Engram.source_turns.through` rebuilds and re-broadcasts the digest on
`post_add`/`post_remove`, gated to turns that already have a usage record.
Four new tests in `frontal_lobe/tests/test_digest.py` (builder-with-tools,
engram add, engram remove, no-usage-record gate). Full pytest suite: 531
passed, 8 skipped, 0 failed.

## In Progress — Nerve Terminal Scan Reconcile (April 11, 2026)

**Status:** Shipped initial fix with test coverage (8 tests, all passing against standalone
smoke harness — Postgres unavailable in sandbox). A regression was caught before close-out:
the UI agent cards "blink on/off" and the refresh button flashes constantly. Root cause is
known, fix is scoped, not yet applied.

**What was shipped:**

- `NerveTerminalStatus.CHECKING = 4` (model const + fixture + data migration
  `peripheral_nervous_system/migrations/0002_checking_status.py`).
- `_run_async_scan` in `peripheral_nervous_system/peripheral_nervous_system.py` now flips
  every live row to CHECKING, probes, upserts pongs to ONLINE, then flips stragglers to
  OFFLINE. Guarded by module-level `_SCAN_LOCK = asyncio.Lock()` to prevent stampede.
- `NerveTerminalRegistryViewSet.list()` (in `peripheral_nervous_system/api.py`) kicks a scan
  via `async_to_sync`, degrades gracefully on scan failure (try/except, logs warning, still
  returns DB state).
- `peripheral_nervous_system/tests/test_nerve_terminal_scan_reconcile.py` — 8 tests
  covering found→online, online→offline, mixed, already-offline untouched, CHECKING is
  transient, concurrent-scan skip, list() triggers scan, list() resilient to scan failure.

**The regression (highest priority when session resumes):**
The scan does per-row `.save()` in three phases, each firing its own acetylcholine. The
frontend subscribes to `NerveTerminalRegistry` broadcasts (`PNSPage.tsx:220`) and calls
`handleRefresh()` on each one, which hits the list endpoint → rekicks the scan (lock skips
the work but the DB returns partially-reconciled CHECKING rows to the UI). Result: UI churn,
blinking cards, blinking refresh button.

**Planned surgical fix (scoped, not started):**

1. Drop `_mark_live_terminals_checking` entirely. No CHECKING transient write — too noisy.
2. `_register_agent_in_db`: compare-then-save. No `.save()` when (status, ip, version)
   already match the discovered identity — kills the "ONLINE over ONLINE" broadcast storm.
3. `_mark_unreachable_offline` stays — these are real state transitions and SHOULD broadcast.
4. Remove the `list()` → scan kick. The scan is already wired to spike execution + the
   explicit `POST /scan` endpoint; piggybacking on every list() means every dendrite
   refetch rekicks a scan.
5. Update tests to match the new broadcast-on-change-only semantics (the CHECKING-transient
   test becomes "CHECKING is never written by the scan" instead).

**Follow-up pass (separate, if Michael wants):**

- Split the monolithic `handleRefresh` on the frontend into per-topic refetchers so a
  `NerveTerminalRegistry` broadcast doesn't also refetch celery-workers / beat / spikes.
- Convert vitals (`/api/v2/vital-signs/vitals/`) from 3s polling to event-driven
  neurotransmitter push from the vitals collector. Currently the ONE sanctioned polling
  exception in PNSPage (line 125). Browser does NOT already have this data.
- Investigate `/api/v2/celery-workers/` 3s response time — likely a synchronous broker
  round-trip inside the view.

## Release Day Update (April 7, 2026)

**Gemma4 rollback:** Gemma4 changed its output format, breaking the Frontal Lobe reasoning loop.
Empirical testing showed Qwen outperformed Gemma4 on the Are-Self framework. Rolled back to Qwen
for release. A parser is being developed to handle Gemma4's new output format post-release.

**OpenRouter sync restored:** The OpenRouter provider sync feature has been brought back but is
untested. Shipping with this feature enabled — needs documentation in are-self-docs.

**READMEs updated:** All four repo READMEs have been updated for release.

## Top Priority — Release Day Documentation (April 7, 2026)

Documentation is the release-day focus. The Docusaurus site has 34 solid pages and 11 UI walkthrough
stubs. See "Ship-Blocking — Documentation Infrastructure" below. Docstrings and drf-spectacular are
also ship-blocking for the API reference.

## Top Priority — Funding & Sponsorship Infrastructure

update the docs with the norepinephrine in the pns for django.

- [ ] **Set up GitHub FUNDING.yml.** _Partially done — `are-self-api/.github/FUNDING.yml` exists with
  `github: [scipraxian]` active. The other platforms are commented out pending account creation (to
  avoid GitHub rendering broken Sponsor buttons). Remaining work is account creation + uncommenting,
  which is out-of-repo._ Create `.github/FUNDING.yml` in are-self-api (org-level). Populate
  with active platform usernames. Platforms to evaluate and set up accounts on:
    - **GitHub Sponsors** (`github: scipraxian`) — native to where the code lives, lowest friction
    - **Ko-fi** — no fees on donations, good for one-time tips, easy setup
    - **Buy Me a Coffee** — similar to Ko-fi, large casual donor base
    - **Patreon** — recurring memberships, good for building a community tier
    - **Open Collective** — transparent finances, good for open-source credibility
    - **Polar** — built for open-source, ties funding to issues/features
    - **LFX Crowdfunding** — Linux Foundation backed, good for institutional credibility
    - **Custom links** — PayPal.me, Venmo, or direct donation page on are-self.com
      Each platform added to FUNDING.yml creates a "Sponsor" button on the GitHub repo. More platforms =
      more eyeballs. Priority: GitHub Sponsors + Ko-fi first, then expand.
- [ ] **Add donation/sponsor links to docs site.** Add a "Support Are-Self" page or section to the
  Docusaurus site with all funding links. Also add to the Discord welcome message.
- [ ] **Explore 501(c)(3) path with Len Lanzi.** Long-term: tax-deductible donations unlock
  institutional and grant funding. Len is the nonprofit connection.

## Top Priority — Move class-constant rows to `genetic_immutables`

Fixture-tier rule change (CLAUDE.md, April 19). The old rule was
"`BEGIN_PLAY` stays in `zygote`, sacred, non-negotiable." The new rule
generalizes it: **rows referenced by a model class constant live in
`genetic_immutables` regardless of which table they live in.** Same reason
`SyncStatus.RUNNING`/`SUCCESS`/`FAILED` are already there — code that
references them by constant must resolve even under the minimal
`CommonTestCase` fixture load (which only pulls `genetic_immutables`).
Keeping `Effector.BEGIN_PLAY` in `zygote` means any new CNS-touching test
that inherits `CommonTestCase` blows up with `DoesNotExist` in a way the
error message won't point at the fixture tier.

**Row moves needed** (source → destination, same app):

- [ ] **`central_nervous_system/fixtures/zygote.json` →
  `central_nervous_system/fixtures/genetic_immutables.json`:**
  `Effector.BEGIN_PLAY`, `LOGIC_GATE`, `LOGIC_RETRY`, `LOGIC_DELAY`,
  `FRONTAL_LOBE`, `DEBUG`. UUIDs are the `uuid.UUID(...)` literals on
  `central_nervous_system/models.py` — frozen, do not regenerate.
- [ ] **`environments/fixtures/zygote.json` →
  `environments/fixtures/genetic_immutables.json`:** `Executable.BEGIN_PLAY`,
  `PYTHON`, `DJANGO`. UUIDs on `environments/models.py`, same frozen-literal
  rule. Any ExecutableArgument / ExecutableSwitch rows that hang off these
  three Executables come along — `genetic_immutables` is the new home for
  the whole canonical-Executable graph.
- [ ] **Verify `SyncStatus.RUNNING` / `SUCCESS` / `FAILED` are already in
  `hypothalamus/fixtures/genetic_immutables.json`** (CLAUDE.md claims so).
  If they're still in zygote, move them too.
- [ ] **Grep for other class-constant UUIDs** in app models to catch any
  stragglers: `rg 'uuid\.UUID\(' --glob '**/models.py'` and cross-check each
  hit against fixture tier placement.

**Test-side cleanup (optional, can follow in a separate commit):**

- [ ] Anything that currently inherits from `CommonFixturesAPITestCase`
  specifically to get `BEGIN_PLAY` or another class-constant Effector/Executable
  can simplify to `CommonTestCase` after the move. Not required — existing
  tests keep passing — but worth a pass once the fixture moves land.
- [ ] Add a regression test: inherit from `CommonTestCase` and assert
  `Effector.objects.get(id=Effector.BEGIN_PLAY)` resolves. That one test
  catches any future drift where someone accidentally moves a class-constant
  row back out of `genetic_immutables`.

**Docs/companion work:** CLAUDE.md (this repo) already updated — the
Standing rulings section, the Fixtures tier description, and the Canonical
Effector / Executable constants section all cite the new rule. No UI-side
change; `nodeConstants.ts` mirrors the class constants by UUID string and
doesn't care which fixture file the row lives in.

## Top Priority — Flip `IdentityAddon` to UUID PK (NeuralModifier-extensible)

Standing project-wide immutability directive (CLAUDE.md): anything a
`NeuralModifier` might contribute rows to uses UUID primary keys. Only integer
PKs remaining are protocol enums and canonical vocabulary tables with class-level
integer constants owned exclusively by core. `IdentityAddon` fails that test —
it is 100% a table a graft would want to add rows to (a bundle could ship a new
phase-2 CONTEXT or phase-4 TERMINAL addon, register its `function_slug`, and
contribute a row). Today it's still an auto-increment integer PK.

- [ ] **Flip `identity.IdentityAddon.id` to `UUIDField(primary_key=True,
  default=uuid.uuid4, editable=False)`**. Update the model; write the migration
  (rename/drop old PK column, add UUID column, backfill via `RunPython` for any
  existing rows, repoint every `ForeignKey`/`ManyToManyField` that references
  it, drop old column). `IdentityAddonPhase` stays integer-PK — it's a fixed
  4-row vocabulary (IDENTIFY / CONTEXT / HISTORY / TERMINAL), core-owned, not a
  graft surface.
- [ ] **Rewrite `identity/fixtures/initial_data.json`** (and wherever else the
  14 current addon rows live — `zygote.json` for Thalamus, identity disc M2M
  arrays in `initial_data.json`) to use UUID strings instead of the integers
  `[5, 7, 8, 9, 10, 11, 12]` etc. Pick fresh `uuid.uuid4()` literals — per the
  Standing ruling these are random, no UUIDv5 or deterministic seeding.
- [ ] **Audit callsites** that hardcode integer PKs:
  `session.identity_disc.addons.filter(function_slug='focus_addon').exists()`
  (TASKS.md:1104) is filter-by-slug and safe. Anything that filters `pk__in=[...]`
  or references an addon by numeric PK needs to flip to UUIDs or — preferably —
  filter by `function_slug`, which is the stable biological identifier anyway.
- [ ] **Consider adding class constants** for the core addons the way
  `Effector.BEGIN_PLAY` etc. work, so code references them by name. Candidates:
  `IdentityAddon.NORMAL_CHAT`, `RIVER_OF_SIX`, `PROMPT`, `YOUR_MOVE`,
  `HIPPOCAMPUS`. If adopted, those rows move to `genetic_immutables` per the
  class-constant rule.
- [ ] **Fixture tier review after the flip.** Addons that ship with core go
  to `initial_phenotypes` (or `genetic_immutables` if class-constant-referenced).
  NeuralModifier-contributed addons live inside the bundle's fixture and come
  in via the install path.

**Why now:** blocking the Thalamus "just normal_chat, nothing else" trim below.
Editing the integer-keyed M2M array today works, but any addon-related fixture
work we do pre-flip just has to get redone post-flip. Worth landing the UUID
migration first and then trimming the Thalamus on top of the new shape.

## Top Priority — Remove Legacy `central_nervous_system/` URL Prefix

- [ ] **The `/central_nervous_system/` URL prefix must GO.** It's a legacy holdover living in the
  wrong place from the old pre-`/api/v2/` routing scheme. The app itself stays (that's the CNS
  brain region); only the URL prefix needs to die. Migrate any still-live endpoints onto
  `/api/v2/` and delete `central_nervous_system.urls.urls` from `config/urls.py`.
- [ ] **After removal, touch nginx again.** `are-self-api/nginx/entrypoint.sh` currently has a
  `location /central_nervous_system/` block proxying to Daphne. Delete that block once the
  Django side is cleaned up, and `docker compose restart nginx` to pick it up.

## Top Priority — PNS Expansion

- [ ] **Multiple Ollama endpoints.** Secondary machine running Ollama should be usable. These are
  **AIModelProviders** — the Hypothalamus already supports multiple providers per model. Add a second
  AIModelProvider record pointing to the secondary machine's `host:port`. The failover strategy handles
  routing. May need a UI affordance in the Hypothalamus to add/edit provider endpoints. Create a scanner
  similar to the scan for agents executable.
- [ ] **Live agent monitoring.** PNS should show active reasoning agents — which IdentityDiscs are
  currently in a session, what they're doing, session duration, turn count. Real-time via existing
  dendrite infrastructure.

## NGINX & MCP Follow-ups

- [ ] **IPv6 upstream noise in nginx logs.** `host.docker.internal` resolves to both IPv4 and
  IPv6; nginx tries the IPv6 address first, fails (`[fdc4:f303:9324::254]:8000 failed`), and
  falls back to IPv4 successfully. Harmless but noisy. Fix by pinning `resolver` to IPv4 only
  in `nginx/entrypoint.sh`, or by using `host-gateway` with an explicit IPv4 alias.
- [ ] **Set up Cloudflare Tunnel so Cowork can reach the MCP (Michael's personal box).**
  Cowork's custom connector flow fetches the endpoint from Anthropic's cloud, so `127.0.0.1`
  is unreachable. Cloudflare Tunnel gives us a publicly-routable hostname backed by an
  outbound-only connection from the local machine — no router/firewall changes, no public
  IP exposure. Steps:
    1. Install `cloudflared` on Windows (MSI from
       `https://github.com/cloudflare/cloudflared/releases` — `cloudflared-windows-amd64.msi`).
       Verify: `cloudflared --version`.
    2. `cloudflared tunnel login` — opens browser, pick `are-self.com`, writes
       `%USERPROFILE%\.cloudflared\cert.pem` (the account credential).
    3. `cloudflared tunnel create are-self-mcp` — prints a UUID and writes
       `%USERPROFILE%\.cloudflared\<uuid>.json` (the tunnel credential).
    4. Create `%USERPROFILE%\.cloudflared\config.yml`:
       ```yaml
       tunnel: are-self-mcp
       credentials-file: C:\Users\micha\.cloudflared\<uuid>.json
       ingress:
         - hostname: mcp.are-self.com
           service: https://local.are-self.com
           originRequest:
             noTLSVerify: false
         - service: http_status:404
       ```
       The origin is `https://local.are-self.com` (not `localhost`) so cloudflared hits the
       upstream with a hostname that matches our real ZeroSSL cert — strict TLS verify stays on.
    5. `cloudflared tunnel route dns are-self-mcp mcp.are-self.com` — creates a Cloudflare
       CNAME to `<uuid>.cfargotunnel.com`. Record is proxied (orange cloud) automatically,
       which is correct for tunnels (unlike the grey-cloud `local.are-self.com` A record).
    6. Foreground test: `cloudflared tunnel run are-self-mcp`, then
       `Invoke-RestMethod -Uri https://mcp.are-self.com/mcp -Method Post -ContentType application/json -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'`
       should return the same 14 tools as the direct-local probe.
    7. Service install (runs on boot, no terminal): `cloudflared service install`.
    8. Add `https://mcp.are-self.com/mcp` as a custom connector in the claude.ai Connectors
       UI. Are-Self must be running (`are-self.bat` + `docker compose up -d`) for Cowork to
       get responses — tunnel alone doesn't start the stack.
       **Per-user only.** This is not a distribution mechanism; each Are-Self user who wants
       Cowork access would have to run their own tunnel with their own subdomain. A real
       shareable "Cowork connects to Are-Self" story is still open and is NOT this task.
- [ ] **Repo cert distribution decision.** Currently `nginx/certs/cert.pem` + `key.pem` live
  outside git. Michael plans to ship the ZeroSSL cert + key in the repo so the 10yo target
  user doesn't have to re-issue one — the cert is for `local.are-self.com` which resolves to
  `127.0.0.1`, so publicly-exposed private-key revocation risk is real but limited (worst case
  an attacker can MITM the user's own localhost traffic, which they already control). Decide
  and document the rationale in `mcp-server.md`. Re-issue + re-commit every ~80 days to stay
  ahead of the 90-day expiry.

## Ship-Blocking — Security Remediation (Before Tuesday Release)

- [x] **~~Pin Django to >=6.0.2.~~** Done — `Django>=6.0.2` is pinned in `requirements.txt` with the
  CVE-2025-64459 comment.
- [x] **~~Pin LiteLLM past the supply chain incident.~~** Done — `litellm>=1.83.0` is pinned in
  `requirements.txt` with a comment calling out the compromised 1.82.7/1.82.8 versions. `--hash`
  verification is still not in place; if we want hash pinning we can do it as a separate pass.
- [x] **~~Update Docker Compose Redis image.~~** Done — `docker-compose.yml` now pins
  `image: redis:7.4.2-alpine` (was `image: redis`, floating to `:latest`). Patched against
  CVE-2025-49844 (CVSS 10.0 RCE in the Redis server Lua scripting engine). Needs a
  `docker compose pull redis && docker compose up -d redis` on the live stack to actually
  swap the running container — the edit alone only affects fresh `up`s.
- [x] **~~Pin DRF to >=3.15.2.~~** Done — `djangorestframework>=3.15.2` is pinned in `requirements.txt`
  with the CVE-2024-21520 comment.
- [x] **~~Remove pygtail from requirements.txt.~~** Done — `pygtail` is no longer in `requirements.txt`.
  Still referenced in TASKS.md (now this line) and `DEPENDENCY_AUDIT.md` as historical notes only.
- [x] **~~Remove unused packages.~~** Done — audited on April 10, 2026. None of `django-htmx`,
  `scapy`, `yapf`, or `aiosmtpd` are present in `requirements.txt` or imported anywhere in
  `are-self-api/`. Only residual references are in TASKS.md and `DEPENDENCY_AUDIT.md` as
  historical notes.
- [x] **~~Separate dev dependencies.~~** Done — `requirements-dev.txt` exists and pulls main via
  `-r requirements.txt`. Contains pytest, pytest-django, pytest-asyncio, coverage, playwright, ruff,
  isort, ipython, plus a type-stubs block (django-stubs, djangorestframework-stubs, celery-types).
  yapf correctly absent (redundant with ruff — tracked under the unused-packages audit above).
- [ ] **Document Ollama security posture.** Users must keep Ollama updated independently. The install
  script should recommend a minimum Ollama version. See DEPENDENCY_AUDIT.md for full CVE list.

## Ship-Blocking — Documentation Infrastructure

- [ ] **Google-style docstrings for all viewsets, serializers, and public methods.** Prerequisite for
  Swagger/OpenAPI auto-generation. Run through each Django app and add docstrings to every ViewSet class,
  every serializer class, and every public method. Format: Google-style (`Args:`, `Returns:`, `Raises:`).
  _Baseline April 10, 2026: 76 ViewSets total, ~25 currently carry a docstring._
  _Biggest gaps — work here first: Hypothalamus (20 VS, ~1 documented), Parietal Lobe (7/0),_
  _PFC (6/0), Hippocampus (2/0). Already in good shape: Temporal Lobe (5/5), Frontal Lobe (2/2)._
  _Priority order: Hypothalamus → Parietal Lobe → PFC → Hippocampus → CNS (9/6) → Identity (7/2) →_
  _PNS (8/4) → environments (8/4) → the rest._
- [ ] **drf-spectacular integration for /api/docs/.** Install `drf-spectacular`, add to INSTALLED_APPS,
  wire `SpectacularAPIView` + `SpectacularSwaggerView` at `/api/docs/`. Generates interactive OpenAPI
  docs from DRF viewsets + docstrings. This gives scientists and developers a try-it-in-the-browser
  API explorer on the running server itself.
- [ ] **Docusaurus docs site (are-self-docs repo).** React-based documentation site deployed via GitHub
  Pages at `are-self.com`. Pulls content from markdown docs in are-self-api and are-self-ui. Sidebar
  navigation, search, versioning. Scaffold is ready — needs content migration and styling.
- [ ] **are-self-research repo.** Separate GitHub repo for whitepapers and academic papers. LaTeX format
  for formal publications. Papers: Focus Economy, Neuro-Mimetic Architecture, LLM Testing Harness,
  CI/CD Sovereignty, Hippocampus Hypergraph Migration (Samuel), Unreal Engine Integration.

## Ship-Blocking — Existing

- [ ] **Hypothalamus — manual model addition.** Need the ability to add a missing model to the
  Hypothalamus by hand through the UI.
- [ ] **CNS / Pathway Editor — favorites and groups.** Cannot set favorites or groups in CNS nor in the
  pathway editor. Need UI affordances for both.
- [ ] **Thalamus message polling.** `api/v2/thalamus/messages` polls excessively when talking to the
  Thalamus. Needs throttling or WebSocket replacement.
- [ ] **Frontal Lobe session Parietal tab — drill-through broken.** Items in the Parietal tab of a
  Frontal Lobe session are not clickable/drillable. Same issue for Parietal actions in the right
  inspector window. Proposed fix: drill to zoom the matching 3D node so the full call is visible.
- [x] **~~Reasoning session deletion.~~** Shipped April 18, 2026 as a UI-only
  change — the existing `ReasoningSessionViewSet` DELETE route (mounted under
  both `/api/v1/` and `/api/v2/` off the same router registry) handles it;
  no backend work was needed. Frontend added a trash-button to each
  cognitive-threads card in `ReasoningPanels.tsx` with stopPropagation +
  confirm, local-state filter, and `onSelectSession('')` when the active
  thread is the one being deleted.
- [ ] **Reasoning session pruning.** DEFERRED. Pick a turn number and click
  "Prune" to delete all turns from that point to the end of the session.
  Michael called this out April 18 — can't just lop turns, the side effects
  (tool calls, engrams, PFC task transitions) have already happened. A real
  prune means respinning or reversing downstream state, which is a much
  bigger design problem. For now, the delete-whole-session flow is the
  escape hatch.
- [ ] **Remove synapse module.** Remove synapse entirely in favor of the new synapse_client.
  _Re-verified April 10, 2026. Five live importers, but the real blocker is narrower than a rename:_
  _- `hippocampus/models.py`, `hippocampus/hippocampus.py`, `identity/models.py`,_
  _  `hypothalamus/models.py` all import `OllamaClient` for one purpose only: calling `.embed()`_
  _ to build vectors. `synapse_client.SynapseClient` has no `embed()` method, so there is no_
  _ drop-in replacement._
  _- `frontal_lobe/synapse_open_router.py` imports `SynapseResponse`, which **does** exist on_
  _  `synapse_client` — that one is a mechanical rename._
  _Real first step: add an embeddings surface (either `SynapseClient.embed()` or a small_
  _dedicated `frontal_lobe/embeddings.py` helper), cut the four model files over, then retire_
  _`frontal_lobe/synapse.py` along with its tests._
- [ ] **Tool call `thought` parameter — make required or improve prompting.** Local models often call
  tools silently (no assistant text). The `thought` parameter exists but isn't required. Either:
  (a) make it required in the tool schema so models must explain themselves, or (b) add system prompt
  instructions demanding tool explanations.
- [ ] **Consolidate and improve MCP engram functions.** The Hippocampus tool functions need cleanup —
  reduce redundancy, improve the interface, make the tool descriptions clearer for small models.
- [ ] **Fix linters / Ruff configuration.** Ensure linting is consistent across the project. Pin Ruff
  config, resolve any conflicting rules.
- [ ] **Rename `system-control` endpoint — off style guide.** "System Control" violates the biological
  naming rule (mechanical/military). Candidates: `homeostasis`, `brainstem`, `medulla`, `autonomic`.
  Coordinated rename with frontend (`SystemControlPanel` → matching name). Frontend task filed under
  are-self-ui/TASKS.md.
- [x] **~~Migrate shutdown endpoint out of dashboard.~~** Canonical endpoint lives at
  `/api/v2/system-control/` (`peripheral_nervous_system/autonomic_nervous_system.py::SystemControlViewSet`)
  with shutdown, restart, and status actions. Deprecated shim in `dashboard/api.py` has been removed along
  with its now-unused imports (`os`, `threading`, `time`, `celery_app`, `AllowAny`-only permission). The
  `/api/v2/system-control/` URL rename (off biological style guide) is tracked separately above.
- [ ] **Standardize API URLs to hyphens.** Legacy underscore routes: `engram_tags`, `reasoning_sessions`,
  `reasoning_turns`, `nerve_terminal_*`. Coordinated with frontend — both repos change together.
  _Verified April 10, 2026: every underscore server route has matching UI consumers_
  _(`EngramEditor.tsx`, `HippocampusPage.tsx`, `SessionChat.tsx`, `ReasoningPanels.tsx`,_
  _`FrontalLobeView.tsx`, `FrontalLobeDetail.tsx`, `ReasoningGraph3D.tsx`, `PNSPage.tsx`).Mechanical sweep — safe once
  greenlit._
- [ ] **Purge residual `/api/v1/` consumers.** Despite the v2 push, the UI still calls
  `/api/v1/node-contexts` (13 sites), `/api/v1/reasoning_sessions/` (7 sites), and
  `/api/v1/environments` (4 sites). Either re-point these to the v2 equivalents or,
  if v2 truly does not host these yet, declare the v2 gap and fill it. Pairs with a
  matching UI cleanup task.
- [ ] **Hypothalamus fixture initial state.** The 4 fixture AIModelProvider records have `is_enabled: true`,
  showing as "Installed" before sync_local runs. Should default to `is_enabled: false` (Available until
  confirmed by sync).
- [x] **~~Share HUMAN_TAG constant.~~** Done — `HUMAN_TAG` lives in `common.constants` and is imported
  into `frontal_lobe/frontal_lobe.py` (line 12) alongside `CONTENT`, `ROLE`, and `USER`. Used via
  `msg[CONTENT] = HUMAN_TAG + '\n' + msg[CONTENT]` in the human-message tagging path. Michael
  verified `river_of_six_addon.py` also imports from `common.constants` rather than defining its
  own copy. Fully consolidated.
- [ ] **IdentityAddonPhase — optional API endpoint.** No ViewSet/router exists for IdentityAddonPhase.
  Frontend hardcodes the 4 phases. If phases ever become user-configurable, a read-only endpoint will
  be needed. Low priority since phases are fixed constants.
- [ ] **`prompt` context variable injection.** The `prompt` context variable is NOT being injected into
  the session's prompt. The context variable resolution chain (spike axoplasm → effector context →
  neuron context) needs auditing — variables are stored but not consumed by `_get_rendered_objective()`
  or wherever the prompt is assembled.

## Completed — CNS Dispatch + Inspector (April 15, 2026)

**Session type:** Cowork (Claude Opus). Triggered by 100% test failures with
`[CNS] No agents online for fleet broadcast.` after migrating to new fixture styles.

**Root cause:** Neuron `3298d2c2` on "List Location R" pathway had a rogue
`distribution_mode = ALL_ONLINE_AGENTS` override (the effector default was
LOCAL_SERVER). The CNSInspector UI had no way to view or edit `neuron.distribution_mode`
or `neuron.environment` — the override was completely invisible.

**Changes shipped (3 files backend, 5 files frontend):**

- [x] **Zero-agent dispatch — no-op, not failure.** `_dispatch_fleet_wave` and
  `_dispatch_first_responder` in `central_nervous_system/central_nervous_system.py`
  now set `SpikeStatus.SUCCESS` + `logger.info` when the NerveTerminalRegistry is
  empty. The local server is not an agent — fleet broadcast to zero targets is a
  no-op. `_dispatch_pinned_wave` (SPECIFIC_TARGETS) left as-is (pinned targets are
  explicit user intent). 4 new tests in `tests/test_routing.py`:
  `CNSFleetBroadcastZeroAgentsTest` (fleet succeeds, graph continues) and
  `CNSFirstResponderZeroAgentsTest` (first-responder succeeds).
- [x] **v2 serializer environment/mode fields.** `NeuronSerializer` in
  `serializers_v2.py` now exposes `environment` (writable FK, nullable),
  `environment_name` (read-only), `distribution_mode_name` (read-only).
  `NeuralPathwaySerializer` exposes `environment` (writable FK, nullable) and
  `environment_name` (read-only). `NeuralPathwayDetailSerializer` inherits both.
  No migrations needed. Tests in `tests/test_effector_editor_api.py`.
- [x] **CNSInspector — Distribution Mode + Environment.** `CNSInspector.tsx` now
  shows a Distribution Mode select (populated from `/api/v2/distribution-modes/`,
  "Inherit from effector" = null, PATCHes neuron) and a Neuron Environment select
  (from `/api/v2/environments/`, same pattern). Yellow override badge when set.
  Types updated in `types.ts`.
- [x] **PathwayInspector — new component.** `PathwayInspector.tsx` renders in the
  right panel of `CNSEditPage.tsx` when no neuron is selected. Exposes pathway-level
  environment editing via PATCH to `/api/v2/neuralpathways/{id}/`.

**Known gap (not blocking):** The v1 serializers (`serializers/serializers.py`) do NOT
expose the new environment fields. If anything still hits v1 routes, the override
remains invisible there. The v1→v2 migration is tracked separately under
"Purge residual `/api/v1/` consumers" below.

## Known Bugs

- [ ] **Modifier Garden Enable button returns 404.** `POST /api/v2/neural-modifiers/<slug>/enable/`
  returns 404 against an installed bundle; `POST /api/v2/neural-modifiers/<slug>/disable/` on the
  same row works. Static analysis of `neuroplasticity/api.py` shows the `enable` and `disable`
  actions as structurally identical (same decorator, same shape, same `loader.enable_bundle` /
  `loader.disable_bundle` call). Test suite's `test_enable_disable_actions` passes, which says
  the automated path returns 200 — so the 404 is almost certainly routing / URL-conf at runtime,
  not code logic. Michael's read: "likely a 1 line fix." Management-command path
  (`./manage.py enable_modifier <slug>`) is unaffected, so this does not block Task 8 being
  driven end-to-end via shell. Blocks FE-2 acceptance through the browser and the Task 8
  live-browser round-trip.

- [ ] **Infinite loop on retry LIMIT REACHED — ROLLED BACK, NEEDS MORE TARGETED FIX.**
  Attempted fix on April 10, 2026 gated `TYPE_FLOW` on all logic effectors
  (LOGIC_GATE / LOGIC_RETRY / LOGIC_DELAY) inside `_process_graph_triggers`. This
  broke real pathways because in practice logic nodes are almost always wired with
  FLOW axons as the downstream connector — suppressing FLOW meant "logic nodes no
  longer fire at all." Rolled back the gating; `_process_graph_triggers` again
  unconditionally appends `AxonType.TYPE_FLOW` to `valid_wire_types` the way it did
  before. The `Effector.LOGIC_EFFECTORS` constant and the two logic-specific
  regression tests (`test_logic_retry_failure_does_not_fire_flow_axon`,
  `test_logic_gate_success_does_not_fire_flow_axon`) were removed with the
  rollback. Kept `test_non_logic_success_still_fires_flow_axon` as a regression
  test for the restored always-fire-FLOW behavior. If the retry short-circuit is
  a real observed issue, the targeted fix is probably narrower: only gate FLOW
  when `effector_id == LOGIC_RETRY` AND `status_id == FAILED` (the "LIMIT REACHED"
  path only), leaving gate/delay and retry's happy path untouched. Michael didn't
  remember this bug, so it may not be reproducible in current pathways.

## Next Up

- [ ] **Swarm message queue — delivery + persistence bug.** Typing a message in the Thalamus chat window
  of a running Frontal Lobe session does not deliver to the session. On refresh, the message is gone — not
  persisted as a ReasoningTurn. Two bugs: (1) swarm_message_queue not receiving/processing inbound messages
  during a live session, (2) messages not saved. **Paired with UI task.**
- [ ] **Error Handler Effector.** A native handler that fires when a spike fails (wired via TYPE_FAILURE
  axon). Reads error context from the axoplasm (`error_message`, `failed_effector`, `result_code`).
  Can dispatch notifications — log to engram, fire a Cortisol neurotransmitter, write a PFC comment on
  the failed task, or escalate to the Thalamus standing session.
- [ ] **Clean requirements.txt.** Pin versions, remove unused/deprecated packages. Verify every package
  is actually imported somewhere. Group by purpose.
- [ ] **Compress fixtures before release.** Compress `initial_data.json` files to single-line JSON for
  Docker release. Keep readable versions in version control.
- [ ] **Expose tool calls in Thalamus chat history.** Check the Vercel AI SDK `parts` schema — tool calls
  should be `tool-call` and `tool-result` parts.
- [ ] **Clear Thalamus chat history from the chat window.** Give the user a way to wipe the visible
  conversation and start fresh. Current state: the Thalamus UI hydrates from
  `GET /thalamus/messages` which walks the most-recent `SpikeTrain` on `NeuralPathway.THALAMUS`
  → most-recent `ReasoningSession` on that train → `get_chat_history(session)`. There is no
  clear / reset action exposed today — the only way to empty the window is a full DB wipe.

  **Backend task:** add `POST /thalamus/clear/` on `ThalamusViewSet` (new `@action(detail=False,
  methods=['post'])`). Cleanest semantics: conclude the active `ReasoningSession` on the
  standing train (status → `CONCLUDED`) so the next `interact` call falls through to the
  genesis branch and spawns a fresh Spike + Session. That preserves history in the DB
  (engrams, tool calls, PFC cross-refs all survive) while making the chat window read empty
  — `messages` walks the *latest* session and a brand-new one has no turns yet. Alternative
  considered and rejected: creating a new `SpikeTrain` so the old one falls off the
  `order_by('-created').first()` lookup — same user-visible outcome, but leaves an orphan
  RUNNING train around and muddies the standing-train invariant. Concluding the session is
  cheaper and keeps the standing train singular.

  **Edge cases:** if no standing train exists, return 200 no-op (nothing to clear).
  If the active session is `ACTIVE` mid-turn, still conclude it — the Frontal Lobe loop checks
  `session.status_id` each turn and will exit cleanly. Fire an Acetylcholine on
  `receptor_class='Thalamus'` with `activity='cleared'` so the UI can drop its local cache
  without a round-trip to `messages`.

  **Companion UI task** (are-self-ui TASKS.md, add there separately): a "Clear chat" /
  trash-can affordance in the Thalamus chat header that POSTs `/thalamus/clear/` and then
  empties the assistant-ui thread state.

  **Test:** post an interact, post a clear, post another interact, GET messages — assert
  only the second round-trip shows. Also assert the old ReasoningSession row is still in
  the DB with status `CONCLUDED` (we're hiding, not destroying).
- [ ] **Prompt_addon state awareness.** The prompt_addon should check session ToolCall history and adapt
  the injected objective accordingly. Without this, small models get stuck in loops re-attempting completed
  steps.
- [ ] **MCP Server.** Have Are-Self be an MCP server, allowing other MCP clients to connect and execute
  commands like Execute Neural Pathway.
- [ ] **MCP Client.** Have Are-Self be an MCP client, calling other MCP servers.
- [ ] **Remove redundant `CREATE EXTENSION vector` steps.** As of Pass 1 UUID migration,
  `common/migrations/0001_initial.py` calls `pgvector.django.VectorExtension()` and every
  `VectorField`-using app depends on it transitively. The manual `CREATE EXTENSION IF NOT EXISTS vector`
  step in `are-self-install.bat` (line 58) and the matching line in the README manual-install
  instructions are now redundant and actively misleading — someone troubleshooting a fresh install
  could waste time chasing whether the extension "ran properly" when Django migrations handle it.
  Remove both. (README already cleaned; `.bat` pending.)
- [x] **~~UUID migration Pass 2 — fixture tier split + Unreal NeuralModifier extraction.~~**
  **DONE (Tasks 1–7 landed on `uuid-migration`, April 11–18).** Pass 1 flipped 18
  NeuralModifier-extensible models from integer to UUID PKs. Pass 2 delivered: the
  four-tier fixture split across every app (`genetic_immutables.json` →
  `zygote.json` → `initial_phenotypes.json` → `petri_dish.json`), the log-merge
  and log-parser moves to `occipital_lobe/` with `LogParserFactory.register()`
  (occipital_lobe/log_parser.py:149), three `environments` models flipped to
  UUID (Task 4.5), the Unreal `modifier_genome/unreal/` scaffold + populated
  `modifier_data.json` (commit `bf2e11d`), the full NeuralModifier lifecycle
  (`build_modifier` + `enable_modifier` / `disable_modifier` /
  `uninstall_modifier` / `list_modifiers`, `neuroplasticity/loader.py`, apps.py
  boot hook, `tests/test_modifier_lifecycle.py` 9 cases, commit `15ceb37`), and
  the docs pass (models.py / CLAUDE.md / STYLE_GUIDE.md "plugin" vocabulary
  scrubbed; April 18). Vocabulary is locked: `neuroplasticity` app,
  `NeuralModifier`, `modifier_genome/`, `neural_modifiers/`, `modifier_data.json`,
  `build_modifier`. No "plugin" in new code. `uuid.uuid4()` only.

  **Superseded planning artifacts (all nuked April 18 after their work landed):**
  `FIXTURE_SEPARATION_PROMPT.md`, `STEP1_REPORT.md`, `STEP1_COMPLETE_REPORT.md`,
  `UUID_MIGRATION_PROMPT.md`, `uuid_migration_mapping.json`, `.step1_backup/`,
  `CC_PROMPT_hypothalamus_uuid_migration.md`, `CC_PROMPT_neuroplasticity_5d_and_6.md`.
  Hypothalamus UUID propagation + UI companion landed in commit `1e98e303`. The
  dead `Executable.UNREAL_*` / `VERSION_HANDLER` / `DEPLOY_RELEASE` class
  constants were removed from `environments/models.py` April 18; `Executable`
  now carries only `BEGIN_PLAY`, `PYTHON`, `DJANGO`.

  **What's left for the NeuralModifier feature area** (Tasks 8–15): dogfood
  the Unreal bundle by moving the three surviving UE-duplicated rows out of
  the new fixture tiers (`mcp_run_unreal_diagnostic_parser` `ToolDefinition`
  in `parietal_lobe/fixtures/zygote.json` + its handler module
  `parietal_lobe/parietal_mcp/mcp_run_unreal_diagnostic_parser.py`, and the
  `"Unreal 5.6.1"` `ProjectEnvironmentType` at pk
  `8a5e6540-92bf-5e73-a26a-4ff3e6185bd9` in
  `central_nervous_system/fixtures/genetic_immutables.json`) plus
  `update_version_metadata` out of core `NATIVE_HANDLERS`; bundle-time
  registration surfaces for the Parietal MCP gateway and `NATIVE_HANDLERS`
  (`register_parietal_tool` / `unregister_parietal_tool` in
  `parietal_lobe/parietal_mcp/gateway.py` + `register_native_handler` /
  `unregister_native_handler` in
  `central_nervous_system/effectors/effector_casters/neuromuscular_junction.py`
  — landed April 18 with 12 new tests, full suite 509 passed / 8 skipped /
  0 failed; no handlers moved, pure plumbing);
  hash-mismatch BROKEN proof; orphan-contribution uninstall path; Parietal
  tool-set status-gating (Task 13 scopes `parietal_lobe/parietal_mcp/`, **not**
  the external `mcp_server/` endpoint — two different MCPs); bundle-author
  docs; upgrade/version/dependency model. Plan lives at
  `NEURAL_MODIFIER_COMPLETION_PLAN.md` in repo root.

  **Standing rulings (Michael):** NeuralModifier bundles install via the
  modifier-garden UI, not via `install.bat`. `initial_data.json` files are
  Michael-only-delete. No UUIDv5/namespaces/deterministic seeding.

- [ ] **Modifier Garden — 3rd-party `NeuralModifier` marketplace.** Are-Self ships with
  3–4 first-party `NeuralModifier` bundles (Unreal first, others TBD), all
  install/uninstall-able via the neuroplasticity API. Beyond the shipped set, stand up
  a "garden" where 3rd parties can publish bundles and users can browse/install them.
  NASA doesn't want Unreal; someone else might. Everything past core is a modifier,
  every modifier is toggleable, and the garden is the discovery layer. Needs:
  publication format (signed bundle?), registry/index service, trust model,
  versioning/compat checks against core, install UI. Depends on Pass 2 Tasks 5–6
  shipping first. Priority: wanted now, not later.

## MCP Server — Phase 2

- [ ] **Cerebrospinal fluid write tool** — Pre-load context data onto spike train cerebrospinal_fluid before launch. Requires wiring into
  NeuronContext or a new cerebrospinal_fluid field on SpikeTrain.
- [ ] **SSE streaming via neurotransmitters** — Use the Synaptic Cleft's neurotransmitter system to stream real-time
  execution updates back through the MCP SSE endpoint. Map Dopamine (success), Cortisol (error), Glutamate (streaming)
  to MCP notifications.
- [ ] **Vector similarity engram search** — Replace text-only search with pgvector cosine similarity search. Requires
  embedding the query via Ollama/Nomic before searching.
- [ ] **Full Thalamus integration** — Wire send_thalamus_message into the actual Thalamus message pipeline with
  WebSocket delivery via Channels.
- [ ] **Authentication layer** — Add token-based auth for the /mcp endpoint. Required before any public deployment.
- [x] **~~Cowork custom connector registration~~** — **DEFERRED.** Claude Desktop/Cowork
  custom connectors require `https://` with strict CA validation. Self-signed certs are
  rejected. Localhost `http://` is rejected. No viable workaround exists without either a
  CA-signed cert for a real domain or Anthropic adding a localhost exception. Tracked
  upstream: `github.com/anthropics/claude-ai-mcp/issues/9`. Are-Self's MCP endpoint
  works correctly — the blocker is on Anthropic's side. Claude Code CAN connect to
  local HTTP MCP servers (no HTTPS needed). NGINX in Docker is configured to auto-upgrade
  to HTTPS if a user provides their own cert in `nginx/certs/`.
- [ ] **Write cerebrospinal fluid tool** — Allow writing arbitrary key-value context data that gets passed to spike train
  execution. This enables programmatic setup of execution context.
- [ ] **Read reasoning session tool** — Expose reasoning session history (turns, tool calls, responses) for
  post-execution analysis.
- [ ] **Migrate are-self-install.bat to Python.** Cross-platform install script (replaces Windows-only .bat). Must
  handle: Python venv, pip install, PostgreSQL check, Redis check, Ollama check. Detect OS via `platform.system()`.
  Target: a 10-year-old runs `python install.py` and everything works.

## Future

- [ ] **Rebuild `core_dump` as `biopsy` — four-tier-aware dumpdata wrapper.** The existing
  `common/management/commands/core_dump.py` is a blacklist-based `dumpdata` wrapper that
  writes one `initial_data.json` per app. After Pass 2 it's obsolete — fixtures live in
  four tiers and a contribution-aware `NeuralModifier` system owns a chunk of the row
  space. Replace with a `biopsy` management command:
  - Preserve the `TRANSACTIONAL_MODELS` blacklist; add `neuroplasticity` to it.
  - Model-level: integer PK → `genetic_immutables.json`. UUID PK → row-level routing.
  - Row-level: rows that are `NeuralModifierContribution` targets are **skipped** (they
    belong to a bundle, not core). A `ZYGOTE_ROWS` allowlist routes to `zygote.json`.
    Everything else routes to `initial_phenotypes.json`.
  - `petri_dish.json` is never generated — it stays hand-maintained.
  - Emit a per-app / per-tier row-count summary at the end of the run.
  Not public-facing; this is a maintenance tool for rebuilding the shipped fixture set
  when structural models change. Pass 2 hand-splits instead of tool-generating, so this
  is post-delivery.
- [ ] **Immutability audit sweep.** Walk every model in the repo and verify the standing
  directive: anything not truly immutable has a UUID primary key. Pass 1 caught 18
  models; Pass 2 Task 4.5 caught three more (`ProjectEnvironmentContextKey`, `Status`,
  `Type`). There are likely a few more lurking in apps that weren't in Pass 1's scope
  (check `parietal_lobe`, `temporal_lobe`, `peripheral_nervous_system`, `prefrontal_cortex`
  especially). Produce a report, then flip anything that shouldn't be integer-keyed in a
  small follow-up migration pass.
- [ ] **Image Generation Effector.** CNS effector pattern: artist LLM writes generation prompt to
  axoplasm, effector POSTs to `{{image_gen_endpoint}}`, saves result, writes path back to axoplasm.
  Decoupled from any specific backend (InvokeAI, ComfyUI, etc.). TTS is already built as Parietal Lobe
  tool — that's the PoC for binary creation.
- [ ] **Branching Canonical Pathway.** Modality routing via logic node. PM/dispatcher inspects PFC task,
  logic node routes based on axoplasm state: code → worker branch, art → artist branch. Depends on
  image generation effector.
- [ ] **Self-improving pathway testing harness.** The testing harness IS a CNS neural pathway — no new
  framework. 7B model + 30B evaluator in a loop. The spike train IS the test run, the axoplasm IS the
  assertion state, the summary_dump IS the test report.
- [ ] **Occipital lobe folder-change detection → environment test pathway.** OS-level file watcher
  (inotify / FSEvents / ReadDirectoryChangesW) lives in `occipital_lobe/` as a visual-cortex-style
  intake layer. Folder change events route to the associated `ProjectEnvironment`'s test-suite
  neural pathway and fire it automatically. Reactive, per-environment — edit a file in a checkout,
  that environment's tests run, results land in the existing spike/neuron/context graph. No new
  models required — uses existing effector/pathway machinery end-to-end. Generalizable beyond
  tests: "watch a folder, fire a pathway" is useful for research dirs, download folders,
  screenshot folders, etc. Occipital lobe as the general OS-event intake region.
- [ ] **Addons as a fourth NeuralModifier registration surface.** Promote the single-hook addon
  contract (callable → `List[Dict]`) into a class with optional lifecycle methods:
  `on_build_payload` (current behavior), `on_pre_tool_call` (veto / fizzle),
  `on_post_tool_call` (state deltas — where the focus/XP ledger goes), `on_turn_end`. Add
  `register_addon` / `unregister_addon` alongside `register_parietal_tool`,
  `register_native_handler`, and `LogParserFactory.register` so bundles can contribute addons
  the same way they contribute tools / handlers / parsers. Flip `IdentityAddon` to UUID-PK
  (same Pass 2 vocabulary-flip pattern as the Hypothalamus vocab). Extract the Focus Game
  into its own bundle as dogfood — mirrors Unreal's role for the other three surfaces.
  `session.current_focus` / `max_focus` / `total_xp` become addon-scoped state rather than
  `ReasoningSession` columns (final storage shape is an open question — see NM plan).

  **Forcing function.** The Focus fizzle at `parietal_lobe/parietal_lobe.py:231-256` runs on
  every tool call regardless of whether the disc has `focus_addon` installed — the addon
  membership check at `identity/addons/focus_addon.py` only decides whether the LLM gets the
  focus prompt injected, not whether the enforcement runs. Thalamus was silently fizzled
  playing a game it couldn't see. The focus/XP ledger at lines 280-287 has the same leak in
  the opposite direction: silent state mutation on every successful tool call for discs that
  never opted in. Long-term fix is this task; short-term stop-gap below.

  **Stop-gap (land independently, deleted when this task lands).** Gate both the fizzle and
  the focus/XP ledger on `session.identity_disc.addons.filter(function_slug='focus_addon').exists()`,
  cached once at `ParietalLobe.__init__` (`sync_to_async`-wrapped — `handle_tool_execution` is
  async) to avoid a DB round-trip per tool call. The existing "Focus Game" `IdentityAddon`
  row (pk=2) has `function_slug=None`, so backfill the slug or add a correctly-slugged row
  as part of the stop-gap or the gate resolves False for every disc and the fix is inert.

  **Blocked on.** NeuralModifier plan reaching end-state (Tasks 8 / 11 / 12 / 15 all landed,
  Surface 1 green on Unreal dogfood). The bundle contribution contract has to hold up under a
  real round-trip before we generalize addons onto it, else we redo both sides if Unreal
  surfaces a reshape. See `NEURAL_MODIFIER_COMPLETION_PLAN.md` → "April 20 design direction —
  addons as a fourth registration surface" for the parallel capture and the open questions
  around addon state storage, hook composition semantics, and whether core-shipped addons
  stay core-registered or move to a notional core bundle.
- [ ] **Nerve Terminal video stream.** Add a third stream alongside STDOUT and log-file tailing: live video
  of the application the terminal is running. Brings the Nerve Terminal to 3 streams total (stdout, log
  file, video). Capture the target app's window/screen on the agent side, encode, and pipe back over the
  existing async generator contract so consumers get frames the same way they get log lines. Needs: capture
  backend (per-OS — likely ffmpeg/gdigrab on Windows, avfoundation on macOS, x11grab on Linux), encoding
  choice (H.264/WebRTC vs. MJPEG over WS), a new `StreamEvent` source (`'video'`) with binary payload
  support, frontend player wired into the existing terminal view, and backpressure/frame-drop handling so
  a slow consumer doesn't stall stdout or log streams.

## Backlog

- [ ] **Test coverage: reasoning loop.** Integration tests for `FrontalLobe.run()` with fixture-backed
  sessions. Verify: turn creation, tool dispatch, `yield_turn` breaks the loop, `mcp_done` creates a
  conclusion, max turns halts, stop signal halts.
- [ ] **Test coverage: Hypothalamus routing.** Unit tests for `pick_optimal_model`: preferred model
  selection, failover strategy steps, budget gate filtering, vector similarity fallback.
  **Partial:** Circuit breaker tests added (April 9, 2026): trip_circuit_breaker increments/backoff,
  cap at 5 min, overflow protection at extreme counter values, trip_resource_cooldown flat 60s with
  no counter change. See `hypothalamus/tests/test_api.py::TestAIModelProviderActions`.
- [ ] **Test coverage: Hippocampus.** Integration tests for engram CRUD: save with vector dedup at 90%
  threshold, update appends text, read links session/spike/identity, search by text and tags.
- [ ] **Test coverage: Parietal Lobe tools.** Test each MCP tool function in isolation with fixture data.
  Verify hallucination armor, focus fizzle gating, XP/focus accounting.
- [ ] **Budget enforcement at request time.** Wire actual spend tracking (sum
  `AIModelProviderUsageRecord.estimated_cost` per period) into the Hypothalamus pre-filter so budgets are
  enforced, not just defined.
- [ ] **Hypothalamus subfamily routing.** Update `pick_optimal_model` to prefer same-subfamily first, then
  parent-family, then vector search.
- [ ] **Audit async usage.** Identify `sync_to_async` wrapping that adds ceremony without value. Primary
  candidates: Frontal Lobe loop, Hippocampus, Parietal Lobe tool execution. Keep async for WebSocket
  streaming (Glutamate), Nerve Terminal, and genuine concurrent I/O. Convert the rest to synchronous with
  a single `sync_to_async` wrap at the Celery boundary.
- [ ] **Stabilize DRF API contract.** Audit all ViewSets and serializers for consistency. Ensure the
  Thalamus chat history endpoint returns the Vercel AI SDK `parts` schema
  (`text` / `reasoning` / `tool-call` / `tool-result`) so the backend matches what
  `are-self-ui/src/components/SessionChat.tsx` already parses. Frontend side is done; this is the
  server-side parity pass.