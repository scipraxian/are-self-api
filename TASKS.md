# Are-Self Task List

Tracked priorities for pushing Are-Self to MIT release. Updated as work completes.

## P0 — Blocking Release

- [ ] **README rewrite.** Replace the Talos UE5 README with Are-Self documentation. Cover: what it is (swarm management
  system / AI reasoning engine), architecture overview (the brain analogy with lobe descriptions), stack, quick start (
  Docker Compose, Ollama, seed, launch), API-first design philosophy, and the mission (free local AI reasoning for
  everyone).
- [ ] **Talos naming sweep.** Rename all `Talos`-prefixed classes, variables, and references. Key targets:
  `TalosEngram` → `Engram`, `TalosEngramTag` → `EngramTag`, `TalosExecutable` → `Executable` (or
  `ExecutableDefinition`), `talos_executable` FK references, `talos_bin` path references in fixtures,
  `TalosHippocampus` → `Hippocampus` (the service class), `seed_talos` management command. Preserve DB migration
  compatibility with `db_table` Meta where needed.
- [ ] **"Spell" / "Cast" naming sweep.** Rename: `cast_cns_spell` → `dispatch_cns_spike` (or similar), `spell_buffer` /
  `append_spell` → `application_buffer` / `append_application`, `GenericEffectorCaster` → `SpikeExecutor` (or similar).
  Touch all references in tasks.py, the effector caster, and templates/views.
- [X] **Style guide in repo.** Drop `STYLE_GUIDE.md` in project root. Pin in Claude Project.
- [X] **Claude Project setup.** Create a Claude Project with the architecture prompt and style guide pinned as project
  knowledge.

## P1 — Architectural Improvements

- [X] **Propagate `thought` parameter to work tools.** Add an optional `thought` string parameter to all MCP tools (
  mcp_git, mcp_fs, mcp_ticket, mcp_engram_save, mcp_engram_update, mcp_query_model, etc.). Update fixture
  `ToolParameterAssignment` records accordingly. The `thought` is logged but not functionally consumed — it forces the
  local model to reason inline with every action.
- [ ] **Audit async usage.** Identify `sync_to_async` wrapping that adds ceremony without value. The Frontal Lobe loop,
  Hippocampus, and Parietal Lobe tool execution are the primary candidates. Keep async for: WebSocket streaming (
  Glutamate), Nerve Terminal, and any genuine concurrent I/O. Convert the rest to synchronous with a single
  `sync_to_async` wrap at the Celery boundary.
- [ ] **Remove deprecated models.** `ModelProvider` and `ModelRegistry` in `frontal_lobe/models.py` are marked
  DEPRECATED. The Hypothalamus (`hypothalamus/models.py`) now owns model routing. Remove the old classes and update any
  remaining references (the `ModelRegistry.NOMIC_EMBED_TEXT` constant in Hippocampus is one — replace with a settings
  constant or direct string).
- [ ] **Remove deprecated `parietal_lobe/registry.py`.** The `ModelRegistry` class in the parietal lobe is a hardcoded
  model map that's been superseded by the Hypothalamus DB-driven routing. Remove it.
- [ ] **Clean up HTMX remnants.** Remove any HTMX-specific views, templates, and URL patterns. The frontend is React
  consuming DRF. The Django side is a pure API.

## P2 — Frontend & API Stabilization

- [ ] **Stabilize DRF API contract.** Audit all ViewSets and serializers for consistency. Ensure the Thalamus chat
  history endpoint (`/sessions/{id}/messages/`) returns the Vercel AI SDK `parts` schema reliably. Document the API
  endpoints (DRF Spectacular or similar).
- [ ] **React frontend integration.** Connect assistant-ui (or chosen React chat framework) to the DRF API. The Thalamus
  already formats messages with `reasoning` and `text` parts — the frontend needs to consume them and render thought
  bubbles vs. assistant messages.
- [ ] **WebSocket streaming for logs.** The Glutamate neurotransmitter system (Axon Hillock → Django Channels) is built.
  Wire the React frontend to subscribe to the appropriate channel groups for live log streaming during spike execution
  and reasoning sessions.

## P3 — Quality & Testing

- [ ] **Test coverage for the reasoning loop.** Integration tests that exercise `FrontalLobe.run()` with fixture-backed
  sessions, identity discs, and tool definitions. Verify: turn creation, tool dispatch, `yield_turn` breaks the loop,
  `mcp_done` creates a conclusion, max turns halts, stop signal halts.
- [ ] **Test coverage for Hypothalamus routing.** Unit tests for `pick_optimal_model`: preferred model selection,
  failover strategy steps, circuit breaker tripping and reset, budget gate filtering, vector similarity fallback.
- [ ] **Test coverage for Hippocampus.** Integration tests for engram CRUD: save with vector dedup at 90% threshold,
  update appends text, read links session/spike/identity, search by text and tags.
- [ ] **Test coverage for Parietal Lobe tools.** Test each MCP tool function in isolation with fixture data. Verify
  argument validation (the hallucination armor in `ParietalMCP.execute`), focus fizzle gating, and XP/focus accounting.

## P4 — Future / Nice to Have

- [ ] **Per-tool `thought` rendering in frontend.** The `thought` parameter on work tools gets logged server-side.
  Expose it through the Thalamus chat history so the frontend can render a timeline of "what the AI was thinking when it
  called mcp_git_commit."
- [ ] **Engram vector search in Thalamus.** Pre-feed relevant engrams into the chat context based on vector similarity
  to the user's message, similar to how the Hippocampus catalog injection works in Turn 1.
- [ ] **Model arena / ELO tracking.** The `AIModelRating` model exists. Build a lightweight evaluation pipeline that
  compares model outputs on identical prompts and updates ELO scores.
- [ ] **Budget enforcement at request time.** The `IdentityBudget` and `IdentityBudgetAssignment` models exist. Wire
  actual spend tracking (sum `AIModelProviderUsageRecord.estimated_cost` per period) into the Hypothalamus pre-filter so
  budgets are enforced, not just defined.

consolodate and improve the mcp engram functions.
fix the linters or ruff or whatever so they are consistent.
