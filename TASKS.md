# Are-Self API — Tasks

Remaining work, sifted for the backend. See FEATURES.md for what's built.

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
- [ ] **Logic node — test coverage.** `pathway_logic_node.py` handles retry counting via provenance chain walking
  and delay via `asyncio.sleep`. Only 1 logic node type exists. Write tests: verify retry count increments correctly
  via provenance, verify delay parameter, verify 200 vs 500 return codes, verify edge cases (no provenance, zero
  retries, zero delay).
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
- [ ] **Migrate shutdown endpoint out of dashboard.** The shutdown action exists in `dashboard/api.py`
  (`celery_app.control.shutdown()` + delayed Django process kill). Needs to move to a non-deprecated app (PNS or
  config) before `dashboard/` is removed. Add a restart endpoint. Frontend buttons needed (tracked in UI tasks).
- [ ] **Standardize API URLs to hyphens.** Legacy underscore routes: `engram_tags`, `reasoning_sessions`,
  `reasoning_turns`, `nerve_terminal_*`. Coordinated with frontend — both repos change together.
- [ ] **Hypothalamus fixture initial state.** The 4 fixture AIModelProvider records have `is_enabled: true`, showing as
  "Installed" before sync_local runs. Should default to `is_enabled: false` (Available until confirmed by sync).

## Next Up

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
- [ ] **Focus economy tuning.** Heavy Extraction (-5 focus) on a starting budget of 5 means one tool call and the
  agent is locked out. The unreal parser specifically may need to be Extraction (-2) instead of Heavy Extraction (-5).
  Alternatively, review starting focus levels — 5 is very tight for multi-step workflows. This is a data/fixture
  change, not a code change.
- [ ] **Addon stage/lifecycle system (stretch).** Currently addons fire in phase order every turn with no awareness
  of session state. A stage system would let addons fire conditionally — e.g., "only inject tool list every N turns"
  or "only fire this addon before the first tool call." Would also allow moving focus mechanics out of mainline
  parietal_lobe code and into a dedicated focus addon. Stretch goal but architecturally sound.
- [ ] **Effector Editor.** Build a proper editor for Effector records. Reference: `EffectorAdmin` in Django admin for
  field layout. Needs full CRUD with all fields exposed.
- [ ] **Logic Node Validation.** The logic node (pathway_logic_node.py) for retry looping and delay needs functional
  validation. Verify provenance chain walking counts correctly, delay works, return codes route properly.
- [ ] **Audit async usage.** Identify `sync_to_async` wrapping that adds ceremony without value. Primary candidates:
  Frontal Lobe loop, Hippocampus, Parietal Lobe tool execution. Keep async for WebSocket streaming (Glutamate), Nerve
  Terminal, and genuine concurrent I/O. Convert the rest to synchronous with a single `sync_to_async` wrap at the
  Celery boundary.
- [ ] **Stabilize DRF API contract.** Audit all ViewSets and serializers for consistency. Ensure Thalamus chat history
  endpoint returns the Vercel AI SDK `parts` schema reliably. Document endpoints (DRF Spectacular or similar).
- [ ] **Docker Compose for full stack.** PostgreSQL and Redis already have Docker configs. Extend to cover Daphne,
  Celery worker, Celery Beat. One `docker compose up` starts everything.

## Recently Completed (April 3, 2026)

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

- [ ] **Reasoning session testing harness.** A dedicated test runner that can replay or simulate reasoning sessions
  with controlled inputs: fixed tool results, predetermined model responses, configurable focus/XP budgets, and
  assertion hooks per turn. Goal: test addon assembly, focus economics, tool gating, river_of_six eviction, and
  prompt_addon state transitions WITHOUT requiring a live LLM or full tick cycle. Should support fixture-backed
  sessions and produce summary_dump-style output for comparison. The session_summary log format is already a good
  starting point for expected-vs-actual comparison.
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
- [ ] **Hypothalamus OpenRouter sync.** Rewrite `_process_openrouter_model()` to use the new
  `_enrich_from_parser(ai_model, parsed)` pattern. Add frontend button. Brings full cloud model catalog with real
  pricing.

## Future

- [ ] **Engram vector search in Thalamus.** Pre-feed relevant engrams into chat context based on vector similarity to
  the user's 