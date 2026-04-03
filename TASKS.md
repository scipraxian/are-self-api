# Are-Self API — Tasks

Remaining work, sifted for the backend. See FEATURES.md for what's built.

## Ship-Blocking

- [ ] **Frontal Lobe node — read identity_disc from context variable.** `_initialize_session()` in
  `frontal_lobe/frontal_lobe.py` creates ReasoningSession with `identity_disc=None`. Line 401 then crashes:
  `ValueError: Session {id} missing IdentityDisc.` Fix: in `run_frontal_lobe()` / `_initialize_session()`, read
  `identity_disc` UUID from the spike's blackboard or NeuronContext variables, then pass it to
  `ReasoningSession.objects.create(identity_disc_id=uuid)`. The Thalamus path hardcodes `IdentityDisc.THALAMUS`,
  the Temporal path passes it explicitly — the CNS path is the only one missing it. **Paired with UI task.**
- [ ] **Lightweight stats endpoint for dashboard.** Create `GET /api/v2/stats/` returning counts for identity discs,
  AI models, and reasoning sessions. The dashboard currently fetches full unpaginated lists just to count — takes
  forever. Single query with `Model.objects.count()` for each.
- [ ] **Tool call `thought` parameter — make required or improve prompting.** Local models often call tools silently
  (no assistant text). The `thought` parameter exists but isn't required. Either: (a) make it required in the tool
  schema so models must explain themselves, or (b) add system prompt instructions demanding tool explanations.
  This pairs with the UI task to render tool calls in chat. Move from Future to here.
- [ ] **Logic node — test coverage.** `pathway_logic_node.py` handles retry counting via provenance chain walking
  and delay via `asyncio.sleep`. Only 1 logic node type exists. Write tests: verify retry count increments correctly
  via provenance, verify delay parameter, verify 200 vs 500 return codes, verify edge cases (no provenance, zero
  retries, zero delay).
- [ ] **"Spell" / "Cast" naming sweep.** Still live in ~9 files. Key targets: `effector_casters/` directory name,
  `cast_cns_spell` in PNS tests, `_extract_variables_from_spell` in CNS serializers, `spell_args`/`spell_switches` in
  CNS models, `Caster` references in tasks.py and tests, `cns_spellbook`/`cns_spell` basenames in CNS URL router.
- [ ] **Remove deprecated frontal_lobe models.** `ModelProvider` and `ModelRegistry` in `frontal_lobe/models.py` are
  still alive with admin registrations, serializers, and `synapse_open_router.py` actively importing them. The
  Hypothalamus owns model routing now. Remove the old classes, update imports, replace
  `ModelRegistry.NOMIC_EMBED_TEXT` constant in Hippocampus with a settings constant or direct string.
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
- [ ] **Effector Editor** see django admin EffectorAdmin
- [ ] **Logic Node Validation**  The logic node for looping etc, needs to be validated.
- [ ] **]
- [ ] **Audit async usage.** Identify `sync_to_async` wrapping that adds ceremony without value. Primary candidates:
  Frontal Lobe loop, Hippocampus, Parietal Lobe tool execution. Keep async for WebSocket streaming (Glutamate), Nerve
  Terminal, and genuine concurrent I/O. Convert the rest to synchronous with a single `sync_to_async` wrap at the
  Celery boundary.
- [ ] **Stabilize DRF API contract.** Audit all ViewSets and serializers for consistency. Ensure Thalamus chat history
  endpoint returns the Vercel AI SDK `parts` schema reliably. Document endpoints (DRF Spectacular or similar).
- [ ] **Docker Compose for full stack.** PostgreSQL and Redis already have Docker configs. Extend to cover Daphne,
  Celery worker, Celery Beat. One `docker compose up` starts everything.

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
- [ ] **Hypothalamus OpenRouter sync.** Rewrite `_process_openrouter_model()` to use the new
  `_enrich_from_parser(ai_model, parsed)` pattern. Add frontend button. Brings full cloud model catalog with real
  pricing.

## Future

- [ ] **Engram vector search in Thalamus.** Pre-feed relevant engrams into chat context based on vector similarity to
  the user's message.
- [ ] **Model arena / ELO tracking.** The `AIModelRating` model exists. Build a lightweight evaluation pipeline that
  compares model outputs on identical prompts and updates ELO scores.
- [ ] **Voice speaking module.** Rust-based TTS integration (from Samuel).
