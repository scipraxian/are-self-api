# Are-Self API — Features

What's built and working in the backend. Organized by brain region.

## Central Nervous System

Directed-graph execution engine. Neural Pathways define graphs of Neurons connected by Axons. Spike Trains
traverse pathways, creating Spikes that execute Effectors (native Python handlers or Celery tasks). Spikes
carry a blackboard (JSON dict) that accumulates context as the train passes through neurons. The CNS is
generic — it doesn't know about AI. It just fires graphs.

NeuroMuscularJunction handles spike dispatch. `_update_status` is the single source of truth for spike
status — sets both `self.status` on the instance and saves to DB. Internal effectors return (200, msg) for
SUCCESS and (500, msg) for FAILURE. N-way spike log merge API with cursor-based delta updates for the
forensics UI. Wire-type logging on axon firing (FLOW/SUCCESS/FAILURE). Deep-copy blackboard between
sibling spikes to prevent nested dict mutation.

**Logic node** supports 3 modes: retry (blackboard-driven loop counting with configurable max_retries and
retry_delay), gate (conditional branching via key/operator/value checks), and wait (pure delay). Config via
NeuronContext keys. Returns SUCCESS or FAILURE axon. 68 tests.

**Debug node (PK 9)** logs blackboard state and neuron context at INFO level. Configurable via `debug_label`.

**Canonical effector PKs:** BEGIN_PLAY=1, LOGIC_GATE=5, LOGIC_RETRY=6, LOGIC_DELAY=7, FRONTAL_LOBE=8,
DEBUG=9. PKs 5-100 reserved for canonical effectors.

**Effector Editor API.** Full CRUD on Effectors, EffectorContexts, EffectorArgumentAssignments, and
CNSDistributionModes. `rendered_full_command` in serializer. Environments app: full CRUD on Executables,
ExecutableArguments, and ExecutableArgumentAssignments.

## Frontal Lobe

Reasoning session engine. `FrontalLobe.run()` executes a `while True` loop: assemble prompt → call LLM →
parse tool calls → dispatch to Parietal Lobe → record turn → repeat. Sessions break on `mcp_done`
(terminal) or `mcp_respond_to_user(yield_turn=True)` (pauses for human input).

Each turn records full telemetry: token counts, inference time, model used, tool calls. Focus economy gates
session length (starting focus: 10, matches max_focus at level 1). Efficiency bonus grants XP for concise
responses. `identity_disc` context variable flows from NeuronContext to session creation.

**Human message tagging.** `<<h>>\n` prepended to swarm_message_queue messages. River of Six only replays
tagged user messages, preventing prompt_addon duplication.

**Stats endpoint.** `GET /api/v2/stats/` returns identity_disc_count, ai_model_count,
reasoning_session_count.

**Narrative dump.** Compact human-readable session briefing: summary from mcp_done, chronological tool
activity, engram list, error summary, token stats.

**Summary dump.** Full INPUT CONTEXT and OUTPUT per turn for debugging what the model saw vs produced.

## Parietal Lobe

Tool execution gateway. `ParietalMCP` dynamically imports and calls MCP tool functions from
`parietal_mcp/mcp_*.py`. Hallucination armor validates tool names, parameter types, and required parameters
before execution. Session and turn IDs injected automatically.

All MCP tools accept an optional `thought` parameter — logged but not consumed functionally. Forces local
models to reason inline with every action.

**TTS tool.** Piper TTS (in-process, no GPU). 5 voice slugs (male/female/child/narrator/whisper), resolves
output path from `audio_root` environment context variable.

## Hippocampus

Vector-embedded long-term memory. Engrams store facts as 768-dimensional vectors (nomic-embed-text via
Ollama). 90% cosine similarity dedup on save. Full provenance chain: each engram links to sessions, turns,
spikes, and IdentityDiscs. Auto-revectorization on description or tag changes. Query param filtering on
EngramViewSet (`?identity_discs=`).

## Hypothalamus

Model selection, routing, and catalog management.

**Catalog sync.** `sync_local` detects installed Ollama models. `fetch_catalog` scrapes ollama.com/library.
Both parse model strings and pass results to the enrichment pipeline.

**Semantic parser.** Standalone, Django-free, MIT-licensed module (98.4% accuracy, 83 tests). Parses model
identifier strings into family, parent family, creator, roles, quantizations, sizes. Sub-families with
parent linkage.

**Resolver.** `_enrich_from_parser` uses `get_or_create` on all reference tables. Wires parent FK on
AIModelFamily. Ollama's `details.parameter_size` overrides parser-extracted value.

**Routing engine.** `pick_optimal_model` with vector-similarity matching between IdentityDisc embeddings
and model catalog. Failover strategies with typed steps. Circuit breakers with scar tissue logic. Per-disc
budget constraints.

**API.** AIModelViewSet (pull, remove, toggle_enabled, sync_local, fetch_catalog), AIModelProviderViewSet
(reset_circuit_breaker, toggle_enabled), FailoverType/Strategy ViewSets, SelectionFilter ViewSet,
AIModelDescription ViewSet with full M2M CRUD. `current_description` resolves model-specific → family
fallback.

**Fixtures.** 4 starter models with $0 pricing, 44 families with descriptions, 35 creators, 48
AIModelDescription records, full routing engine (3 strategies, 4 failover types, 8 steps, 3 selection
filters). Tiered catalog fixtures: ollama_popular.json (39 models), ollama_complete.json (74 models).

## Identity

Blueprint system for AI personas. Identities define system prompt templates (Django template syntax with
runtime variables), enabled tools, addon phases (IDENTIFY, CONTEXT, HISTORY, TERMINAL), and model routing
preferences via AIModelSelectionFilter.

Identities forge into IdentityDiscs — deployed instances with their own level, XP, success/failure record,
and memory. IdentityDiscs are vector-embedded (768-dim, nomic-embed-text) with auto-regeneration on
prompt, type, tag, or addon changes. Budget system with 3 periods and 4 budgets.

## Temporal Lobe

Iteration lifecycle management. Iteration Definitions are blueprints with shift columns (Sifting →
Pre-Planning → Planning → Executing → Post-Execution → Sleeping), each with turn limits. Incepting a
definition creates a live Iteration bound to an Environment. Auto-populate definitions with all 6 shift
types on create.

## Synaptic Cleft

Real-time event bus on Django Channels (WebSocket). Typed neurotransmitter events: Dopamine (success),
Cortisol (errors), Acetylcholine (data sync), Glutamate (streaming), Norepinephrine (monitoring).
Norepinephrine with celery_signals.py for task_prerun, task_postrun, worker_ready.

## Peripheral Nervous System

Fleet management. CeleryWorkerViewSet with real-time worker status via Norepinephrine. Celery Beat drives
the tick cycle as the system heartbeat.

## Environments

Project context with full CRUD. Context variables (key-value pairs) resolve in executable paths and
templates via Django's template engine. Single active environment at a time. Inline context key creation.
Full CRUD on Executables, ExecutableArguments, and ExecutableArgumentAssignments.

## Prefrontal Cortex

Task management. Epics → Stories → Tasks assigned to IdentityDiscs. The Frontal Lobe picks up tasks from
the PFC backlog when reasoning sessions start.

## Thalamus

Chat relay. Formats messages with `reasoning` and `text` parts for the Vercel AI SDK schema. Standing
session support via ThalamusChat. Message injection into active sessions via `swarm_message_queue`.

## System Control

Shutdown/restart/status endpoints at `/api/v2/system-control/`. Shutdown kills Celery workers + delayed
process exit. Restart spawns new worker + restarts Beat. Status returns workers_online, beat_running,
timestamp.

## Project Infrastructure

**Install and launch scripts.** `are-self-install.bat` handles first-time setup end-to-end: venv, deps,
Docker, pgvector, migrations, fixtures, superuser, Ollama, embedding model. `are-self.bat` launches the
full stack.

**Style guide** (STYLE_GUIDE.md). Google Python Style Guide baseline with Are-Self overrides: no nested
functions, constants on model classes, targeted error handling, verbose bracketed logging, intentional async
policy, established mixin hierarchy, real-database testing with fixtures.
