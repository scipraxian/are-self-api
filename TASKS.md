# Are-Self API — Tasks

Remaining work, sifted for the backend. See FEATURES.md for what's built.

## Top Priority — Image & Audio Manipulation

Image and audio generation are **CNS effectors**, not Parietal Lobe tools. The artist LLM reasons and
writes a generation prompt to the blackboard. A generation effector reads that prompt, POSTs to whatever
image/audio server is configured via environment context variables, saves the output file, and writes the
file path back to the blackboard. The Frontal Lobe node after the effector can review the result.

This completely decouples Are-Self from any specific generation backend. The effector just calls a URL.
InvokeAI (MIT licensed), ComfyUI, stable-diffusion.cpp — whatever's listening at `{{image_gen_endpoint}}`
does the work. Swap backends by changing one environment variable.

**TTS** is already built as a Parietal Lobe tool (`mcp_tts`) using Piper (in-process, no GPU, no server).
Image/audio generation that requires a GPU and a separate process uses the effector pattern instead.

## Ship-Blocking

support multiple ollama endpoints locally.... my secondary machine is running ollama, i want to be able to use it.

- [X] **Frontal Lobe — context variable injection into session.** identity_disc context variable now flows to
  `ReasoningSession.objects.create()` (fixed 4/3), but the `prompt` context variable is NOT being injected into the
  session's prompt. The context variable resolution chain (spike blackboard → effector context → neuron context) needs
  auditing — variables are stored but not consumed by `_get_rendered_objective()` or wherever the prompt is assembled.
  Verify the full flow: NeuronContext → raw_context dict → rendered objective → session prompt.
- [x] **Frontal Lobe — swarm_message_queue <<h>> tagging.** Human messages from swarm_message_queue now get
  `<<h>>\n` prepended in `_build_turn_payload`. River of Six only replays `<<h>>`-tagged user messages,
  preventing prompt_addon duplication. Tests pass. TODO: move `HUMAN_TAG` constant to shared location,
  use `ROLE`/`CONTENT` constants in frontal_lobe.py instead of raw strings.
- [X] **Frontal Lobe — swarm_message_queue delivery + persistence.** Typing a message in the Thalamus chat window
  of a running Frontal Lobe session does not deliver the message to the running session. On refresh, the typed
  message is also gone — not persisted. Two bugs: (1) swarm_message_queue not receiving/processing inbound messages
  during a live session, (2) messages not being saved as ReasoningTurns on send.
- [x] **Lightweight stats endpoint for dashboard.** Created `GET /api/v2/stats/` in `config/api.py`. Returns
  `identity_disc_count`, `ai_model_count`, `reasoning_session_count` via `Model.objects.count()`.
- [ ] **Tool call `thought` parameter — make required or improve prompting.** Local models often call tools silently
  (no assistant text). The `thought` parameter exists but isn't required. Either: (a) make it required in the tool
  schema so models must explain themselves, or (b) add system prompt instructions demanding tool explanations.
  This pairs with the UI task to render tool calls in chat.
- [x] **Logic node — rewrite + test coverage.** `pathway_logic_node.py` rewritten to 3 modes (retry/gate/wait)
  with blackboard-driven config instead of provenance walking. 49 tests in `test_logic_node.py` (expanded Session 7).
  Config via NeuronContext keys: `logic_mode`, `max_retries`, `retry_delay` (retry mode), `delay` (wait mode),
  `gate_key`, `gate_operator`, `gate_value`. Returns 200 (SUCCESS axon) or 500 (FAILURE axon).
- [X] **"Spell" / "Cast" naming sweep.** Still live in ~9 files. Key targets: `effector_casters/` directory name,
  `cast_cns_spell` in PNS tests, `_extract_variables_from_spell` in CNS serializers, `spell_args`/`spell_switches` in
  CNS models, `Caster` references in tasks.py and tests, `cns_spellbook`/`cns_spell` basenames in CNS URL router.
- [x] **Remove deprecated frontal_lobe models.** `ModelProvider` and `ModelRegistry` removed from `models.py`,
  `admin.py`, `serializers.py`. `synapse_open_router.py` refactored to string-only (deprecated, no production
  callers). `NOMIC_EMBED_TEXT_MODEL` constant replaces DB lookup in Hippocampus. `hypothalamus/models.py` stray
  import removed. Migration `0004` drops tables. Hippocampus tests updated.
- [ ] **Remove deprecated `parietal_lobe/registry.py`.** Hardcoded model map still exists. Superseded by Hypothalamus
  DB-driven routing.
- [ ] **Consolidate and improve MCP engram functions.** The Hippocampus tool functions need cleanup — reduce
  redundancy, improve the interface, make the tool descriptions clearer for small models.
- [ ] **Fix linters / Ruff configuration.** Ensure linting is consistent across the project. Pin Ruff config, resolve
  any conflicting rules.
- [ ] **Migrate shutdown endpoint out of dashboard.** ⚠️ SHIP-BLOCKER. The shutdown action exists in `dashboard/api.py`
  (`celery_app.control.shutdown()` + delayed Django process kill). Needs to move to a non-deprecated app (PNS or
  config) before `dashboard/` is removed. Add a restart endpoint. Frontend buttons needed (tracked in UI tasks).
  Without this, developers must manually kill/restart Celery workers when deploying code changes — stale workers
  run old native handlers and produce confusing errors (e.g., "No handler found for slug: debug_node").
- [ ] **Standardize API URLs to hyphens.** Legacy underscore routes: `engram_tags`, `reasoning_sessions`,
  `reasoning_turns`, `nerve_terminal_*`. Coordinated with frontend — both repos change together.
- [ ] **Hypothalamus fixture initial state.** The 4 fixture AIModelProvider records have `is_enabled: true`, showing as
  "Installed" before sync_local runs. Should default to `is_enabled: false` (Available until confirmed by sync).

## Next Up

- [x] **Logic Node Verification (gates testing harness AND branching pathways).** DONE. The logic node
  (`pathway_logic_node.py`) was rewritten to 3 modes with blackboard-driven config:
  1. **Retry mode:** Reads `loop_count` from blackboard (no provenance walking), increments, checks
     against `max_retries`. Deep copy fix applied in `central_nervous_system.py`.
  2. **Gate mode:** Checks blackboard keys with operators: exists, equals, not_equals, gt, lt.
     Returns 200 (SUCCESS axon) or 500 (FAILURE axon). This is the switch for modality routing.
  3. **Wait mode:** Pure delay, always passes.
  16 tests written in `test_logic_node.py`. Both capabilities verified — testing harness and
  modality routing are now unblocked.
- [ ] **Error Handler Effector.** A native handler that fires when a spike fails (wired via TYPE_FAILURE
  axon). Reads error context from the blackboard (`error_message`, `failed_effector`, `result_code`).
  Can dispatch notifications — log to engram, fire a Cortisol neurotransmitter, write a PFC comment on
  the failed task, or escalate to the Thalamus standing session. Multiple notification types, configured
  via effector command args. Every non-trivial pathway should have a failure wire leading here.
- [ ] **Image Generation Effector — PoC (Option A).** Prove the generation effector pattern works with a
  dedicated art pathway (separate from the canonical temporal pathway):
  - **Effector caster:** `image_generation_caster.py`. Reads `generation_prompt` from the blackboard,
    POSTs to `{{image_gen_endpoint}}` (environment context variable), saves result to
    `{{media_root}}/filename.png`, writes file path back to blackboard. ~30 lines. Uses `requests.post()`.
  - **Fixture:** New Effector record for the image generation effector.
  - **Pathway:** 3-node art pathway — Frontal Lobe (artist writes prompt to BB) → Generation Effector
    (calls external service) → Frontal Lobe (reviews result, iterates or done).
  - **Identity template:** Artist IdentityDisc with creative prompting addons.
  - **Acceptance criteria:** Artist LLM writes an image prompt, effector generates an image via external
    service, file lands on disk at the environment-configured path.
  - **Addon candidate:** This is Are-Self's first addon — "install the effector, configure the endpoint,
    it works." Docker Compose profile: `docker compose --profile art up` adds InvokeAI.
- [ ] **Branching Canonical Pathway (Option B — after logic node).** Evolve the temporal tick to support
  modality routing. The canonical pathway's first node (PM/dispatcher) inspects the PFC task and mangles
  the blackboard. A logic node routes based on blackboard state: code tasks → worker branch, art tasks →
  artist branch (includes generation effector), default → existing behavior. One beat, one pathway, N
  execution paths. **Depends on:** logic node verification, PoC effector proven.
- [ ] **Effector Editor.** Build a proper editor for Effector records. Reference: `EffectorAdmin` in Django admin for
  field layout. Needs full CRUD with all fields exposed.
- [ ] **Self-improving pathway testing harness (zero new code).** The testing harness IS a CNS neural pathway.
  No new framework needed — use the existing architecture:
    - **Node A:** Frontal Lobe effector, 7B model, given a task prompt via identity/addon config
    - **Node B:** Frontal Lobe effector, 30B evaluator model, reads Node A's session output. Job: "Did it work?
      If not, use the DB tool to UPDATE Node A's prompt, then fail."
    - **Logic Node:** Loop controller. Blackboard tracks iteration count. On Node B failure → loop back to Node A
      with the improved prompt. On success → done.
    - **Acceptance criteria:** Can a 7B with 10 focus make a useful memory in 10 turns on 8GB RAM?
    - **Prerequisites:** Logic node must work (verify provenance chain walking, loop counting via blackboard,
      delay parameter). Node B needs a "prompt editor" tool in the Parietal Lobe (or just the existing DB update
      tool pointed at IdentityAddon/prompt_addon content).
    - The spike train IS the test run. The blackboard IS the assertion state. The summary_dump IS the test report.
- [ ] **Clean requirements.txt.** Pin versions, remove unused/deprecated packages (`pygtail` is marked
  deprecated, `scapy` may be unused, `django-htmx` was for the removed HTMX views). Verify every package
  is actually imported somewhere. Group by purpose (Django core, async/channels, testing, AI/ML, tools).
- [ ] **Compress fixtures before release.** All `initial_data.json` fixture files are human-readable with
  generous whitespace. For the Docker release, compress to single-line JSON or use Django's `--format`
  option. Keep the readable versions in version control, generate compressed copies at build time.
- [ ] **Expose tool calls in Thalamus chat history.** The session chat endpoint needs to include tool call details
  (tool name, arguments, result) in the response so the frontend can render them. Currently invisible turns when
  models work silently. Check the Vercel AI SDK `parts` schema — tool calls should be `tool-call` and `tool-result`
  parts.
- [ ] **Prompt_addon state awareness.** The prompt_addon re-injects the same static objective every turn, even after
  the model has already completed early steps. Observed in session 2d46beb8: prompt kept saying "use the parser ONCE"
  after it had already been called. The prompt_addon should check session ToolCall history and adapt the injected
  objective accordingly — e.g., "parser already ran, process results and save engrams." This isn't an addon doing the
  agent's job — it's giving the agent accurate situational context. Without this, small models get stuck in loops
  re-attempting completed steps.
- [x] **Focus economy tuning — starting focus raised to 10.** `ReasoningSession.current_focus` default changed from
  5 to 10 (matches `max_focus` at level 1). Agents now start with full focus instead of half. Heavy Extraction (-5)
  now allows two tool calls before needing synthesis, not one-and-done. The unreal parser may still need to be
  reclassified from Heavy Extraction (-5) to Extraction (-2) — that's a fixture change.
- [X] **Re-enable efficiency bonus.** `ReasoningTurn.apply_efficiency_bonus()` is commented out. The data source for
  output length is now known (`model_usage_record.response_payload`). Re-enable so XP comes from being concise, not
  just from tool use. The leveling system is half-wired without it.
- [ ] **Addon stage/lifecycle system (stretch).** Currently addons fire in phase order every turn with no awareness
  of session state. A stage system would let addons fire conditionally — e.g., "only inject tool list every N turns"
  or "only fire this addon before the first tool call." Would also allow moving focus mechanics out of mainline
  parietal_lobe code and into a dedicated focus addon. Stretch goal but architecturally sound.

- [ ] **Audit async usage.** Identify `sync_to_async` wrapping that adds ceremony without value. Primary candidates:
  Frontal Lobe loop, Hippocampus, Parietal Lobe tool execution. Keep async for WebSocket streaming (Glutamate), Nerve
  Terminal, and genuine concurrent I/O. Convert the rest to synchronous with a single `sync_to_async` wrap at the
  Celery boundary.
- [ ] **Stabilize DRF API contract.** Audit all ViewSets and serializers for consistency. Ensure Thalamus chat history
  endpoint returns the Vercel AI SDK `parts` schema reliably. Document endpoints (DRF Spectacular or similar).
- [ ] **Docker Compose for full stack.** PostgreSQL and Redis already have Docker configs. Extend to cover Daphne,
  Celery worker, Celery Beat. One `docker compose up` starts everything.

## Recently Completed (April 4, 2026 — Session 7)

- [x] **Logic node test coverage expanded (18 → 49 tests).** New test classes: RetryDelayTest (3),
  RetryLifecycleTest (1), ContextKeyConstantsTest (8). Expanded existing: RetryModeTest (+6), GateModeTest (+10
  including LT operator coverage, unknown operator, non-numeric, whitespace, None blackboard), WaitModeTest (+2),
  UnknownModeTest (+2 for case-insensitivity and whitespace trimming). Tests exercise edge cases: negative/non-numeric
  max_retries, blackboard preservation across retries, limit-reached-does-not-increment, retry_delay vs delay key
  separation. File: `central_nervous_system/tests/test_logic_node.py`.
- [x] **retry_delay key standardized.** Retry mode uses `CTX_RETRY_DELAY = 'retry_delay'` (matching frontend
  RetryNeuronNode). Wait/delay mode keeps `CTX_DELAY = 'delay'` (matching DelayNeuronNode). No backward compat
  fallback — one key per mode, period. Frontend and backend now agree.
- [x] **SystemControlViewSet.** Shutdown/restart/status endpoints at `/api/v2/system-control/`. Shutdown kills
  Celery workers + delayed os._exit. Restart spawns new worker process + restarts Beat if running. Status returns
  `workers_online`, `beat_running`, `timestamp`.
- [x] **CNS execution wire-type logging.** `_process_graph_triggers` now logs wire type labels (FLOW/SUCCESS/FAILURE)
  per axon firing. This confirmed the infinite loop root cause (FLOW axon firing after LIMIT REACHED).

## Known Bugs — Session 7

- [ ] **Infinite loop on retry LIMIT REACHED.** The retry logic node correctly returns 500 (LIMIT REACHED), firing
  the FAILURE axon. BUT if the graph has a FLOW axon (type 1) from the retry neuron to a downstream node, that FLOW
  wire ALSO fires — because FLOW axons fire regardless of spike status. The user deleted the stale FLOW wire and
  recreated it as SUCCESS, but the loop still continues. This means the bug is deeper than a stale wire. Investigate
  `_process_graph_triggers` in `central_nervous_system/central_nervous_system.py` — when a logic node (effector PKs
  5, 6, 7) finishes, FLOW axons should NOT fire. Only SUCCESS or FAILURE should fire based on the result code. This
  is the #1 bug.
- [ ] **CNS Monitor view never refreshes.** After clicking Start and navigating to `/cns/spiketrain/:id`, the graph
  shows initial state then never updates. Dendrite subscriptions use `useDendrite('Spike', spiketrainId)` and
  `useDendrite('SpikeTrain', spiketrainId)` — but events may not be scoped to the spiketrain ID on the backend.
  Check that `fire_neurotransmitter` in the spike lifecycle uses `dendrite_id=str(spike.spike_train_id)` so the
  frontend subscription actually matches. Also check `trainTerminalRef` isn't getting set prematurely.

## Recently Completed (April 4, 2026 — Session 6)

- [x] **Debug node effector (PK 9).** New native handler `debug_node.py` that logs blackboard state and
  neuron context at INFO level. Registered in `NATIVE_HANDLERS` dict in `neuromuscular_junction.py`.
  Fixture: Effector PK 9 (executable PK 19, `is_favorite=true`). Executable PK 19 added to environments
  fixture (`internal=true`, `executable="debug_node"`).
- [x] **CNS execution logging.** Added `logger.info` at: train START (pathway name), spike creation
  (neuron ID, effector name, provenance), local dispatch, finalize (active spike count or terminal status).
  `_log_info` in NMJ upgraded from `logger.debug` to `logger.info` with spike ID prefix. Explicit log
  before native handler execution with slug and effector name.
- [x] **Frontal Lobe effector PK 171 → 8 fixture fix.** Added deprecated PK 171 record back to fixture
  (`"Frontal Lobe Node (Deprecated)"`) so existing DB records don't cause IntegrityError on fixture reload.

## Recently Completed (April 4, 2026 — Session 5)

- [x] **Frontal Lobe effector PK moved from 171 to 8.** Consistent with the canonical PK range (5-8).
  Updated in `models.py` (Effector.FRONTAL_LOBE), fixture (effector, effector_context, 2 neuron references).
- [x] **Canonical effector PK constants.** `Effector.BEGIN_PLAY=1, LOGIC_GATE=5, LOGIC_RETRY=6,
  LOGIC_DELAY=7, FRONTAL_LOBE=8` in `central_nervous_system/models.py`. Mirrored in frontend
  `nodeConstants.ts`. These PKs are fixture-defined and stable.

## Recently Completed (April 4, 2026 — Session 4)

- [x] **Logic node rewrite — 3 modes.** `pathway_logic_node.py` rewritten from single retry mode to
  retry/gate/wait. Config via NeuronContext keys instead of command string parsing. Blackboard-driven
  loop counting replaces provenance walking. Gate mode enables conditional branching (the switch for
  modality routing). 16 tests in `test_logic_node.py`.
- [x] **Shallow blackboard copy → deepcopy.** `central_nervous_system.py` changed 3 instances of
  `.blackboard.copy()` to `copy.deepcopy()`. Prevents nested dict mutation leaking between sibling spikes.
- [x] **Re-enable efficiency bonus.** `ReasoningTurn.apply_efficiency_bonus()` re-enabled. Gated on
  Focus Addon presence (only called from `focus_addon()`, so no addon = no bonus). Added early return
  for turn 1 (no previous output). Tests written and passing.
- [x] **mcp_tts Parietal Lobe tool.** `parietal_lobe/parietal_mcp/mcp_tts.py` built with Piper TTS
  (in-process, no GPU). 5 voice slugs (male/female/child/narrator/whisper), resolves output path from
  `audio_root` environment context variable. Fixture entries added (ToolDefinition PK 29, assignments,
  parameter enums). `piper-tts` added to requirements.txt.
- [x] **Fixture constraint fix.** Removed duplicate ToolParameter PK 63 (name="text") — reused
  existing PK 50. Assignment PK 173 updated to point to PK 50. Also fixed truncated JSON at end of
  parietal_lobe fixture (missing closing braces).
- [x] **EnvironmentEditor "+ Key" button.** Added inline creation of new context variable keys via
  POST to `/api/v2/context-keys/`. Auto-selects new key after creation.
- [x] **Image/audio architecture documented.** CNS effector pattern — artist LLM writes prompt to
  blackboard, generation effector POSTs to external service, result path written back. Completely
  decoupled from any specific backend (InvokeAI, ComfyUI, etc.).

## Recently Completed (April 3, 2026 — Session 3)

- [x] **Remove deprecated frontal_lobe models.** `ModelProvider` and `ModelRegistry` deleted from `models.py`,
  `admin.py`, `serializers.py`. `synapse_open_router.py` simplified to string-only (deprecated, no production
  callers). `NOMIC_EMBED_TEXT_MODEL` constant in `frontal_lobe/models.py` replaces two async DB lookups in
  Hippocampus `save_engram()` and `update_engram()`. `hypothalamus/models.py` stray import removed. Migration
  `0004_remove_modelprovider_modelregistry` drops both tables. `frontal_lobe/fixtures/initial_data.json` cleaned
  (ModelProvider and ModelRegistry entries removed — only ReasoningStatus remains). Hippocampus tests updated
  to remove `mock_registry_get` patches.
- [x] **Session analysis — 7B model loop diagnosis.** Analyzed `session_summary_2d46beb8.log` (qwen2.5-coder:7b).
  Identified 4 interacting causes: static prompt_addon re-injecting "call parser ONCE" after it was already called,
  aggressive river_of_six eviction losing tool results, 20K parser payload exceeding context budget, Heavy Extraction
  focus cost (-5) on a 5-focus budget giving exactly one shot. Recommended prompt_addon state awareness as the key
  fix. Added tasks for focus economy tuning and addon stage/lifecycle system.

## Recently Completed (April 3, 2026 — Session 2)

- [x] **Fizzle message tool name fix.** `parietal_lobe.py` fizzle error referenced nonexistent `mcp_save_memory` —
  corrected to `mcp_engram_save`. Models were unable to recover from fizzle states because the suggested recovery
  tool didn't exist. (Fixed by Michael 4/3.)
- [x] **Session summary_dump endpoint.** `GET /api/v2/reasoning_sessions/{id}/summary_dump/` returns a compact
  text log showing INPUT CONTEXT (all addon-assembled messages per turn with role, content preview, tool calls)
  and OUTPUT (provider-agnostic response extraction). Uses plain HttpResponse (not streaming — ASGI incompatible).
- [x] **<<h>> human message tagging.** Solved prompt duplication bug where prompt_addon's user message was
  replayed by river_of_six. Human swarm messages tagged with `<<h>>`, river_of_six skips untagged user messages.
- [x] **Lightweight list serializer for BBB dashboard.** `ReasoningSessionMinimalSerializer` with annotation-based
  `turns_count` for fast dashboard loading.
- [ ] **Share HUMAN_TAG constant.** `HUMAN_TAG = '<<h>>'` lives in `river_of_six_addon.py` but `frontal_lobe.py`
  uses the raw string `'<<h>>\n'`. Move to a shared constants file. Also use existing `ROLE` constant instead of
  raw `'user'` string in frontal_lobe.py.
- [ ] **IdentityAddonPhase — optional API endpoint.** No ViewSet/router exists for IdentityAddonPhase.
  Frontend hardcodes the 4 phases (IDENTIFY=1, CONTEXT=2, HISTORY=3, TERMINAL=4). If phases ever become
  user-configurable, a read-only endpoint will be needed. Low priority since phases are fixed constants.

## Backlog

- [ ] **Test coverage: reasoning loop.** Integration tests for `FrontalLobe.run()` with fixture-backed sessions.
  Verify: turn creation, tool dispatch, `yield_turn` breaks the loop, `mcp_done` creates a conclusion, max turns
  halts, stop signal halts.
- [ ] **Test coverage: Hypothalamus routing.** Unit tests for `pick_optimal_model`: preferred model selection, failover
  strategy steps, circuit breaker tripping/reset, budget gate filtering, vector similarity fallback.
- [ ] **Test coverage: Hippocampus.** Integration tests for engram CRUD: save with vector dedup at 90% threshold,
  update appends text, read links session/spike/identity, search by text and tags.
- [ ] **Test coverage: Parietal Lobe tools.** Test each MCP tool function in isolation with fixture data. Verify
  hallucination armor, focus fizzle gating, XP/focus accounting.
- [ ] **Budget enforcement at request time.** Wire actual spend tracking (sum
  `AIModelProviderUsageRecord.estimated_cost` per period) into the Hypothalamus pre-filter so budgets are enforced,
  not just defined.
- [ ] **Hypothalamus subfamily routing.** Update `pick_optimal_model` to prefer same-subfamily first, then
  parent-family, then vector search.
- [ ] **Hypothalamus OpenRouter sync (clean import).** Rewrite `_process_openrouter_model()` to use the new
  `_enrich_from_parser(ai_model, parsed)` pattern and the standalone semantic parser (98.4% accuracy). Previous
  attempt borked the database with junk records — the parser should now prevent that by properly classifying
  families, roles, quantizations, and rejecting unrecognizable entries. Add frontend button. `synapse_open_router.py`
  is dead code and can be deleted — this sync uses the Hypothalamus routing layer, not the old OpenRouter client.

## Future

- [ ] **Engram vector search in Thalamus.** Pre-feed relevant engrams into chat context based on vector simila